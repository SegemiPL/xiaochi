"""A completed-turn boundary: internal reasoning and tools never enter public history."""
from __future__ import annotations

import re
from collections.abc import Iterable

from qwen_agent.llm.schema import Message

from src.config.product import AGENT_NAME, DISCLAIMER

INCOMPLETE_ANSWER = '暂时未能形成完整答复。请补充问题或材料后重试。'
_INTERNAL_BLOCK = re.compile(
    r'<(think|thinking|analysis|tool_call|function_call)\b[^>]*>.*?(?:</\1\s*>|\Z)',
    re.IGNORECASE | re.DOTALL,
)


def public_text(text: str) -> str:
    """Remove embedded internal blocks and attach the footer exactly once."""
    text = _INTERNAL_BLOCK.sub('', text).strip()
    while text.endswith(DISCLAIMER):
        text = text[:-len(DISCLAIMER)].rstrip()
    return f'{text or INCOMPLETE_ANSWER}\n\n{DISCLAIMER}'


def completed_answer(messages: Iterable[Message | dict], agent_name: str = AGENT_NAME) -> str:
    """Only accept a final main-agent message after every tool result/call.

    If a run ends on a tool, a specialist, or reasoning alone, earlier planning
    text cannot be mistaken for its final answer. Call only after the generator ends.
    """
    frames = list(messages)
    if not frames:
        return public_text('')
    last = frames[-1]
    if (last.get('role') != 'assistant' or last.get('function_call') or last.get('tool_calls')
            or (last.get('name') and last.get('name') not in {agent_name, '3wagent', '小池'})):
        return public_text('')
    content = last.get('content')
    if isinstance(content, list):
        content = ''.join(str(item.get('text') or '') for item in content)
    return public_text(content if isinstance(content, str) else '')


def legacy_public_history(messages: list[dict]) -> list[dict]:
    """Project old internal transcripts without exporting their tools or inlined files."""
    result, responses = [], []

    def flush():
        if responses:
            result.append({'role': 'assistant', 'content': completed_answer(responses)})
        responses.clear()

    for message in messages:
        if message.get('role') == 'user':
            flush()
            content = message.get('content')
            if isinstance(content, list):
                content = '\n'.join(str(item.get('text') or '') for item in content)
            # Old agents replaced uploaded files with complete private parsed bodies.
            content = re.sub(r'<uploaded_document\b.*?</uploaded_document>',
                             '[附件]', str(content or ''), flags=re.DOTALL)
            result.append({'role': 'user', 'content': content, 'attachments': []})
        elif message.get('role') in {'assistant', 'function', 'tool'}:
            responses.append(message)
    flush()
    return result
