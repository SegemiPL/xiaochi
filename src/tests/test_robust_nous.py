"""Raw Nous calls are repaired before the upstream parser loses information."""

import json

from qwen_agent.llm.schema import ASSISTANT, ContentItem, Message
from src.llm.robust_nous import RobustNousFnCallPrompt, repair_nous_tool_call_text


def test_missing_opening_quote_on_arguments_is_repaired():
    malformed = '''<tool_call>
{"name": "WebSearchTool",
arguments": {"jurisdiction": "CN", "query": "税收公告"}}
</tool_call>'''

    repaired = repair_nous_tool_call_text(malformed)
    body = repaired.split("<tool_call>\n", 1)[1].split("\n</tool_call>", 1)[0]

    assert json.loads(body) == {
        "name": "WebSearchTool",
        "arguments": {"jurisdiction": "CN", "query": "税收公告"},
    }


def test_repair_handles_newlines_trailing_commas_and_braces_inside_strings():
    malformed = '''<tool_call>{name: 'WebSearchTool', arguments: {
      url: 'https://example.com/a?x={value}', max_chars: 8000,
    }}</tool_call>'''

    repaired = repair_nous_tool_call_text(malformed)
    prompt = RobustNousFnCallPrompt()
    parsed = prompt.postprocess_fncall_messages(
        [Message(ASSISTANT, [ContentItem(text=repaired)])]
    )

    assert parsed[0].function_call.name == "WebSearchTool"
    assert json.loads(parsed[0].function_call.arguments) == {
        "url": "https://example.com/a?x={value}",
        "max_chars": 8000,
    }


def test_ambiguous_or_incomplete_call_remains_untouched():
    incomplete = '<tool_call>{"name":"WebSearchTool", arguments": {'

    assert repair_nous_tool_call_text(incomplete) == incomplete
