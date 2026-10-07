"""FastAPI boundary that exposes final answers, never Agent execution frames."""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.agent.conversations import ConversationStore
from src.attachments.registry import supported_suffixes
from src.config.attachments import ATTACHMENT_SETTINGS
from src.config.llm import MissingAPIKeyError
from src.config.product import PRODUCT
from src.config.runtime import WORKSPACE_DIR
from src.web.markdown import render_answer
from src.web.service import BusyError, ChatService

STATIC_DIR = Path(__file__).with_name('static')
LOGGER = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(default='', max_length=20_000)
    attachments: list[str] = Field(default_factory=list, max_length=5)
    request_id: UUID | None = None


def create_app(*, agent_factory=None, store=None, upload_root=None) -> FastAPI:
    if agent_factory is None:
        def agent_factory():
            from src.agent.main_agent import MainAgent
            from src.config.llm import load_llm_config
            return MainAgent(llm=load_llm_config())

    store = store or ConversationStore()
    upload_root = Path(upload_root or WORKSPACE_DIR / 'web_uploads')
    service = ChatService(store, agent_factory, upload_root)
    app = FastAPI(title='小弛', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.chat_service = service

    @app.middleware('http')
    async def same_origin_mutations(request: Request, call_next):
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            origin = request.headers.get('origin')
            if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
                from fastapi.responses import JSONResponse
                return JSONResponse({'detail': '请从小弛页面发起请求。'}, status_code=403)
        return await call_next(request)

    def existing(conversation_id):
        try:
            record = service.public_record(conversation_id)
            for message in record["messages"]:
                if message["role"] == "assistant":
                    message["html"] = render_answer(message["content"])
            return record
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, '对话不存在。') from None

    @app.get('/api/config')
    def config():
        return {key: PRODUCT[key] for key in ('name', 'tagline', 'disclaimer', 'quick_questions')}

    @app.get('/api/conversations')
    def conversations():
        summaries = []
        for item in store.list():
            try:
                record = service.public_record(item['id'])
            except FileNotFoundError:
                continue  # Deleted after the list snapshot was read.
            summaries.append({key: record[key] for key in ('id', 'title', 'created_at', 'updated_at')})
        return {'conversations': summaries}

    @app.post('/api/conversations', status_code=201)
    def new_conversation():
        return service.public_record(store.create())

    @app.get('/api/conversations/{conversation_id}')
    def conversation(conversation_id: str):
        return existing(conversation_id)

    def change_history(conversation_id: str, *, restore: bool = False):
        try:
            service.change_history(conversation_id, restore=restore)
        except BusyError as exc:
            raise HTTPException(409, str(exc)) from None
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, '对话不存在。') from None
        return {'id': conversation_id, 'restored' if restore else 'deleted': True}

    @app.delete('/api/conversations/{conversation_id}')
    def delete_conversation(conversation_id: str):
        return change_history(conversation_id)

    @app.post('/api/conversations/{conversation_id}/restore')
    def restore_conversation(conversation_id: str):
        return change_history(conversation_id, restore=True)

    @app.get('/api/conversations/{conversation_id}/progress/{request_id}')
    def progress(conversation_id: str, request_id: UUID):
        existing(conversation_id)
        try:
            return service.progress.snapshot(str(request_id), conversation_id)
        except KeyError:
            raise HTTPException(404, '暂无本次请求的进度。') from None

    @app.post('/api/conversations/{conversation_id}/attachments', status_code=201)
    async def upload(conversation_id: str, file: Annotated[UploadFile, File()]):
        existing(conversation_id)
        name = Path((file.filename or '').replace('\\', '/')).name
        if not name or name in {'.', '..'} or Path(name).suffix.lower() not in supported_suffixes():
            await file.close()
            raise HTTPException(400, '暂不支持此文件格式。请上传 PDF、DOCX、表格或文本文件。')
        upload_id = uuid.uuid4().hex
        directory = upload_root / conversation_id / upload_id
        (directory / "file").mkdir(parents=True)
        target = directory / "file" / name
        size = 0
        try:
            with target.open('wb') as handle:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > ATTACHMENT_SETTINGS.max_file_size_mb * 1024 * 1024:
                        raise HTTPException(413, f'文件不能超过 {ATTACHMENT_SETTINGS.max_file_size_mb} MB。')
                    handle.write(chunk)
            if not size:
                raise HTTPException(400, '文件为空，请重新选择。')
            (directory / 'metadata.json').write_text(json.dumps({'name': name}), encoding='utf-8')
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        return {'id': upload_id, 'name': name}

    @app.post('/api/conversations/{conversation_id}/messages')
    def chat(conversation_id: str, body: ChatRequest):
        existing(conversation_id)
        text = body.message.strip()
        if not text and not body.attachments:
            raise HTTPException(400, '请输入问题或上传材料。')
        try:
            result = service.answer(conversation_id, text, body.attachments,
                                    str(body.request_id) if body.request_id else None)
        except BusyError as exc:
            raise HTTPException(409, str(exc)) from None
        except MissingAPIKeyError:
            raise HTTPException(503, '服务尚未配置模型，请联系维护人员完成配置。') from None
        except (FileNotFoundError, ValueError):
            raise HTTPException(400, '材料或模型配置不可用，请检查配置后重试。') from None
        except Exception:
            LOGGER.exception('Xiaochi turn failed')
            raise HTTPException(502, '暂时无法完成查询，请稍后重试。') from None
        return {**result, 'answer_html': render_answer(result['answer'])}

    @app.get('/')
    def index():
        return FileResponse(STATIC_DIR / 'index.html')

    app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')
    return app
