"""Serialized agent execution and separate public/private conversation histories."""
from __future__ import annotations

import copy
import json
import re
import threading
from collections.abc import Callable
from pathlib import Path

from qwen_agent.llm.schema import ContentItem, Message

from src.agent.attachments import inline_uploaded_files
from src.agent.conversations import ConversationStore, conversation_title
from src.agent.progress import progress_sink, report_progress
from src.agent.public_answer import completed_answer, legacy_public_history, public_text
from src.attachments.storage import register_session_document, reset_session_documents
from src.config.product import AGENT_NAME
from src.web.progress import ProgressTracker

# Existing runtime run IDs and attachment-session state are process globals.
# A single process executes one question at a time until these become request-scoped.
_RUN_LOCK = threading.Lock()


class BusyError(RuntimeError):
    pass


class ChatService:
    def __init__(self, store: ConversationStore, agent_factory: Callable,
                 upload_root: Path):
        self.store, self.agent_factory, self.upload_root = store, agent_factory, upload_root
        self.progress = ProgressTracker()

    def public_record(self, conversation_id: str) -> dict:
        record = self.store.load(conversation_id)
        display = record.get('public_messages')
        if display is None:
            display = legacy_public_history(record['messages'])
        # Explicit allowlist; never send the raw store record to an API response.
        messages = []
        for item in display:
            role = item.get('role')
            if role not in {'user', 'assistant'}:
                continue
            text = str(item.get('content') or '')
            if role == 'assistant':
                text = public_text(text)
            messages.append({
                'role': role, 'content': text,
                'attachments': [str(name) for name in item.get('attachments', [])]
                if role == 'user' else [],
            })
        return {**{key: record[key] for key in ('id', 'title', 'created_at', 'updated_at')},
                'title': conversation_title(messages), 'messages': messages}

    def attachment(self, conversation_id: str, upload_id: str) -> dict:
        if not re.fullmatch(r'[0-9a-f]{32}', upload_id):
            raise ValueError('Invalid attachment ID')
        directory = self.upload_root / conversation_id / upload_id
        metadata = json.loads((directory / 'metadata.json').read_text(encoding='utf-8'))
        path = (directory / 'file' / metadata['name']).resolve()
        path.relative_to(directory.resolve())
        if not path.is_file():
            raise FileNotFoundError('Attachment unavailable')
        return {'name': metadata['name'], 'path': path}

    def change_history(self, conversation_id: str, *, restore: bool = False) -> None:
        # A running answer must finish saving before its history can be removed.
        if not _RUN_LOCK.acquire(blocking=False):
            raise BusyError('正在处理问题，请待答复完成后再管理历史对话。')
        try:
            if restore:
                self.store.restore(conversation_id)
            else:
                self.store.delete(conversation_id)
        finally:
            _RUN_LOCK.release()

    def answer(self, conversation_id: str, text: str, attachment_ids: list[str],
               request_id: str | None = None) -> dict:
        if not _RUN_LOCK.acquire(blocking=False):
            raise BusyError('正在处理另一条问题，请稍后再试。')
        failed = True
        try:
            if request_id:
                self.progress.start(request_id, conversation_id)
            with progress_sink(
                (lambda stage: self.progress.update(request_id, stage)) if request_id else None
            ):
                result = self._answer(conversation_id, text, attachment_ids)
            failed = False
            return result
        finally:
            if request_id:
                self.progress.finish(request_id, failed=failed)
            reset_session_documents()
            _RUN_LOCK.release()

    def _answer(self, conversation_id: str, text: str, attachment_ids: list[str]) -> dict:
        record = self.store.load(conversation_id)
        public = self.public_record(conversation_id)['messages']
        files = [self.attachment(conversation_id, item) for item in attachment_ids]
        history = [Message(**item) for item in copy.deepcopy(record['messages'])]
        if files:
            content = [ContentItem(text=text)] if text else []
            content += [ContentItem(file=str(item['path'])) for item in files]
        else:
            content = text
        history.append(Message(role='user', content=content))
        reset_session_documents()
        for message in history:
            body = message.content
            if isinstance(body, list):
                body = '\n'.join(item.text or '' for item in body)
            for document_id in re.findall(r'<uploaded_document\s+id="([0-9a-f]+)"', body):
                register_session_document(document_id)
        report_progress('reading' if files else 'preparing')
        resolution = inline_uploaded_files(history[-1])
        final_frame = []
        # Do not yield frames or store them publicly during execution.
        if resolution.should_block:
            answer = public_text("暂时无法读取这份附件，请补充具体问题或重新上传可读取的文件。")
            final_frame = [Message(role="assistant", content=answer, name=AGENT_NAME)]
        else:
            report_progress('thinking')
            agent = self.agent_factory()
            for frame in agent.run(history):
                final_frame = frame
            answer = completed_answer(final_frame, getattr(agent, "name", AGENT_NAME))
        report_progress('writing')
        history.extend(final_frame)
        public += [
            {'role': 'user', 'content': text, 'attachments': [item['name'] for item in files]},
            {'role': 'assistant', 'content': answer},
        ]
        self.store.save(conversation_id, history, public_messages=public)
        return {'conversation_id': conversation_id, 'answer': answer}
