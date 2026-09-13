"""Lossless repairs for common malformed Nous textual tool calls."""

from __future__ import annotations

import copy
import json
import re

import json5
from qwen_agent.llm.fncall_prompts.nous_fncall_prompt import NousFnCallPrompt
from qwen_agent.llm.schema import ContentItem

_COMPLETE_TOOL_CALL_RE = re.compile(
    r"<tool_call>(?P<body>.*?)</tool_call>",
    re.DOTALL,
)
_NAME_RE = re.compile(r'''["']?name["']?\s*:\s*["'](?P<name>[^"']+)["']''')
_ARGUMENTS_RE = re.compile(r'''["']?arguments["']?\s*:\s*''')


class RobustNousFnCallPrompt(NousFnCallPrompt):
    """Repair recoverable raw text before Qwen-Agent's lossy fallback parser."""

    def postprocess_fncall_messages(self, messages, **kwargs):
        repaired = copy.deepcopy(messages)
        for message in repaired:
            if not isinstance(message.content, list):
                continue
            content: list[ContentItem] = []
            for item in message.content:
                if item.get_type_and_value()[0] != "text":
                    content.append(item)
                    continue
                content.append(ContentItem(text=repair_nous_tool_call_text(item.text or "")))
            message.content = content
        return super().postprocess_fncall_messages(repaired, **kwargs)


def install_robust_nous_parser(model) -> None:
    """Install once on Qwen-Agent models that use the textual Nous protocol."""
    prompt = getattr(model, "fncall_prompt", None)
    if isinstance(prompt, NousFnCallPrompt) and not isinstance(prompt, RobustNousFnCallPrompt):
        model.fncall_prompt = RobustNousFnCallPrompt()


def repair_nous_tool_call_text(text: str) -> str:
    """Canonicalize complete calls when name and argument boundaries are clear."""

    def replace(match: re.Match) -> str:
        body = match.group("body").strip()
        try:
            parsed = json5.loads(body)
        except (TypeError, ValueError):
            parsed = _salvage_call(body)
        if not isinstance(parsed, dict):
            return match.group(0)
        name = parsed.get("name")
        arguments = parsed.get("arguments")
        if not isinstance(name, str) or not name.strip() or not isinstance(arguments, dict):
            return match.group(0)
        canonical = json.dumps(
            {"name": name.strip(), "arguments": arguments},
            ensure_ascii=False,
        )
        return f"<tool_call>\n{canonical}\n</tool_call>"

    return _COMPLETE_TOOL_CALL_RE.sub(replace, text)


def _salvage_call(body: str) -> dict | None:
    name_match = _NAME_RE.search(body)
    arguments_match = _ARGUMENTS_RE.search(body)
    if name_match is None or arguments_match is None:
        return None
    object_text = _balanced_object(body, arguments_match.end())
    if object_text is None:
        return None
    try:
        arguments = json5.loads(object_text)
    except (TypeError, ValueError):
        return None
    if not isinstance(arguments, dict):
        return None
    return {"name": name_match.group("name"), "arguments": arguments}


def _balanced_object(text: str, start: int) -> str | None:
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    quote = ""
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None
