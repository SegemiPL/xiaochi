"""Normalize provider-specific textual tool calls at the model boundary."""

from __future__ import annotations

import copy
import html
import json
import re
from collections import Counter
from collections.abc import Iterator
from typing import Any

import json5
from qwen_agent.llm.schema import ASSISTANT, ContentItem, FunctionCall, Message

from src.llm.robust_nous import install_robust_nous_parser

_DSML_MARKER = r"[|｜]{1,2}DSML[|｜]{1,2}"
_DSML_INVOKE = re.compile(
    rf'<{_DSML_MARKER}\s+invoke\s+name=(?P<quote>["\'])(?P<name>.+?)(?P=quote)\s*>'
    rf"(?P<body>.*?)\\?</{_DSML_MARKER}\s+invoke\s*>",
    re.DOTALL,
)
_DSML_ARGUMENTS = re.compile(
    rf'<{_DSML_MARKER}\s+parameter\s+name=(?P<quote>["\'])arguments(?P=quote)'
    rf"(?:\s+string=(?:[\"\'])?(?:false|true)(?:[\"\'])?)?\s*>"
    rf"(?P<arguments>.*?)\\?</{_DSML_MARKER}\s+parameter\s*>",
    re.DOTALL,
)
_DSML_CALLS_TAG = re.compile(rf"\\?</?{_DSML_MARKER}\s+calls\s*>", re.DOTALL)
_TOOL_CALL = re.compile(r"<tool_call>\s*(?P<call>.*?)\s*</tool_call>", re.DOTALL)


class ToolCallCompatibilityMixin:
    """Validate provider tool calls before ``FnCallAgent`` can execute them."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        model = getattr(self, "llm", None)
        if model is not None:
            install_robust_nous_parser(model)

    def _call_llm(
        self,
        messages: list[Message],
        functions: list[dict] | None = None,
        stream: bool = True,
        extra_generate_cfg: dict | None = None,
    ) -> Iterator[list[Message]]:
        yield from self._call_llm_compat(
            messages=messages,
            functions=functions,
            stream=stream,
            extra_generate_cfg=extra_generate_cfg,
            allow_retry=True,
        )

    def _call_llm_compat(
        self,
        *,
        messages: list[Message],
        functions: list[dict] | None,
        stream: bool,
        extra_generate_cfg: dict | None,
        allow_retry: bool,
    ) -> Iterator[list[Message]]:
        output = super()._call_llm(
            messages=messages,
            functions=functions,
            stream=stream,
            extra_generate_cfg=extra_generate_cfg,
        )
        allowed_names = _function_names(functions)
        final_issue: str | None = None
        for frame in output:
            normalized = normalize_textual_tool_calls(frame) if functions else frame
            normalized, issue = normalize_native_tool_calls(normalized, allowed_names)
            if _has_runaway_repetition(normalized):
                # Stop consuming the HTTP stream immediately.  Continuing to
                # inspect later cumulative frames lets a local model burn the
                # whole context window even though the answer is already in a
                # stable repetition cycle.
                final_issue = "repetitive_output"
                close = getattr(output, "close", None)
                if callable(close):
                    close()
                break
            if issue:
                # Qwen-Agent's Nous parser can turn malformed JSON into a native
                # FunctionCall with a polluted name.  Never yield such a frame:
                # FnCallAgent executes every yielded function call immediately.
                final_issue = issue
                continue
            final_issue = None
            yield normalized

        if final_issue and allow_retry:
            correction = (
                "Your previous response could not be used because it contained a malformed "
                "tool call or runaway repetition. Try once more. If calling a tool, emit exactly "
                "one valid call using a listed function name and a JSON object for arguments. "
                "Otherwise give the concise final answer now without repeating your planning."
            )
            retry_messages = copy.deepcopy(messages) + [Message(role="user", content=correction)]
            yield from self._call_llm_compat(
                messages=retry_messages,
                functions=functions,
                stream=stream,
                extra_generate_cfg=extra_generate_cfg,
                allow_retry=False,
            )
        elif final_issue:
            yield [
                Message(
                    role=ASSISTANT,
                    content=(
                        "本轮模型连续生成了无法安全执行的工具调用或重复内容，系统已停止该输出。"
                        "请重试本问题；先前的异常工具调用没有被执行。"
                    ),
                )
            ]


def normalize_textual_tool_calls(messages: list[Message]) -> list[Message]:
    """Convert complete DeepSeek DSML invocations to Qwen ``FunctionCall`` messages.

    Native function-call messages and ordinary assistant text pass through
    unchanged. Incomplete or unrecognized DSML also remains text so this layer
    never invents an executable call from ambiguous output.
    """
    normalized: list[Message] = []
    for message in messages:
        if message.role != ASSISTANT or message.function_call:
            normalized.append(message)
            continue
        text = _message_text(message)
        matches, parsed_calls = _parse_dsml_calls(text)
        if not parsed_calls:
            matches, parsed_calls = _parse_tool_call_tags(text)

        if not parsed_calls:
            normalized.append(message)
            continue

        prefix = _DSML_CALLS_TAG.sub("", text[: matches[0].start()]).strip()
        if prefix:
            normalized.append(
                Message(
                    role=ASSISTANT,
                    content=prefix,
                    reasoning_content=message.reasoning_content,
                    name=message.name,
                    extra=copy.deepcopy(message.extra),
                )
            )
        for index, (name, arguments) in enumerate(parsed_calls, start=1):
            extra = copy.deepcopy(message.extra) or {}
            extra["function_id"] = str(index)
            normalized.append(
                Message(
                    role=ASSISTANT,
                    content="",
                    reasoning_content=(
                        message.reasoning_content if index == 1 and not prefix else None
                    ),
                    function_call=FunctionCall(name=name, arguments=arguments),
                    name=message.name,
                    extra=extra,
                )
            )
    return normalized


def normalize_native_tool_calls(
    messages: list[Message],
    allowed_names: set[str],
) -> tuple[list[Message], str | None]:
    """Repair only unambiguous native calls and reject unsafe parser output.

    The upstream Nous fallback parser is deliberately permissive.  A missing
    quote before ``arguments`` can produce a name such as
    ``WebSearchTool\", arguments\": {...`` and empty/non-JSON arguments.  Tool
    names are repaired only when one allowed name is an unambiguous prefix;
    arguments must still decode to an object before the call may execute.
    """
    normalized: list[Message] = []
    for message in messages:
        if message.role != ASSISTANT or not message.function_call:
            normalized.append(message)
            continue

        call = message.function_call
        name = str(call.name or "").strip()
        if name not in allowed_names:
            prefix_matches = [candidate for candidate in allowed_names if name.startswith(candidate)]
            if len(prefix_matches) != 1:
                return [], "invalid_tool_name"
            name = prefix_matches[0]

        arguments = _strict_json_object(call.arguments)
        if arguments is None:
            return [], "invalid_tool_arguments"
        repaired = copy.deepcopy(message)
        repaired.function_call = FunctionCall(name=name, arguments=arguments)
        normalized.append(repaired)
    return normalized, None


def _function_names(functions: list[dict] | None) -> set[str]:
    names: set[str] = set()
    for function in functions or []:
        name = function.get("name_for_model") or function.get("name")
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return names


def _strict_json_object(value: Any) -> str | None:
    if isinstance(value, dict):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = json5.loads(value)
        except (TypeError, ValueError):
            return None
    else:
        return None
    if not isinstance(parsed, dict):
        return None
    return json.dumps(parsed, ensure_ascii=False)


def _has_runaway_repetition(messages: list[Message]) -> bool:
    """Detect a long suffix repeated three times in content or reasoning."""
    for message in messages:
        for value in (_message_text(message), str(message.reasoning_content or "")):
            compact = re.sub(r"\s+", " ", value).strip()
            if len(compact) < 1200:
                continue
            tail = compact[-6000:]
            # Paragraph-sized blocks catch the observed planning loop without
            # flagging ordinary repeated legal terminology or table rows.
            for size in (800, 600, 400, 250):
                if len(tail) < size * 3:
                    continue
                block = tail[-size:]
                if tail[-size * 3 : -size * 2] == block and tail[-size * 2 : -size] == block:
                    return True
            paragraphs = [item.strip() for item in re.split(r"\n\s*\n", value) if item.strip()]
            if len(paragraphs) >= 5 and paragraphs[-1] == paragraphs[-3] == paragraphs[-5]:
                return True
            # Local reasoning models often repeat a multi-paragraph planning
            # cycle rather than one fixed byte-aligned suffix.  Count long
            # normalized paragraphs and sentences in the recent tail so the
            # cycle is detected regardless of its period or stream boundary.
            units = paragraphs + [
                item.strip()
                for item in re.split(r"(?<=[.!?。！？])\s+", value)
                if item.strip()
            ]
            normalized_units = [re.sub(r"\s+", " ", item) for item in units if len(item) >= 80]
            if any(count >= 4 for count in Counter(normalized_units).values()):
                return True
    return False


def _parse_dsml_calls(text: str) -> tuple[list[re.Match], list[tuple[str, str]]]:
    matches = list(_DSML_INVOKE.finditer(text))
    parsed_calls: list[tuple[str, str]] = []
    for match in matches:
        arguments_match = _DSML_ARGUMENTS.search(match.group("body"))
        if arguments_match is None:
            return matches, []
        name = html.unescape(match.group("name")).strip()
        arguments = html.unescape(arguments_match.group("arguments")).strip()
        # Some rendered transcripts escape underscores for Markdown.
        arguments = arguments.replace(r"\_", "_")
        if not name or not arguments:
            return matches, []
        parsed_calls.append((name, arguments))
    return matches, parsed_calls


def _parse_tool_call_tags(text: str) -> tuple[list[re.Match], list[tuple[str, str]]]:
    matches = list(_TOOL_CALL.finditer(text))
    parsed_calls: list[tuple[str, str]] = []
    for match in matches:
        try:
            call = json5.loads(match.group("call"))
        except (TypeError, ValueError):
            return matches, []
        if not isinstance(call, dict) or not isinstance(call.get("name"), str):
            return matches, []
        arguments = call.get("arguments", {})
        if isinstance(arguments, str):
            serialized_arguments = arguments
        elif isinstance(arguments, dict):
            serialized_arguments = json.dumps(arguments, ensure_ascii=False)
        else:
            return matches, []
        parsed_calls.append((call["name"].strip(), serialized_arguments))
    return matches, parsed_calls


def _message_text(message: Message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(_content_item_text(item) for item in content or [])


def _content_item_text(item: ContentItem | dict) -> str:
    if isinstance(item, dict):
        return str(item.get("text") or "")
    return str(item.text or "")
