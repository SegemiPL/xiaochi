"""Provider-specific textual tool calls are normalized at one boundary."""

from qwen_agent.llm.schema import ASSISTANT, FunctionCall, Message
from src.agent.tool_call_compat import (
    ToolCallCompatibilityMixin,
    _has_runaway_repetition,
    normalize_native_tool_calls,
    normalize_textual_tool_calls,
)

DSML_RESPONSE = r"""I'll verify the official source.

<｜｜DSML｜｜ calls>
<｜｜DSML｜｜ invoke name="YamlReadTool">
<｜｜DSML｜｜ parameter name="arguments" string="false">{"file\_path": "config/output-contract.yaml"}\</｜｜DSML｜｜ parameter>
\</｜｜DSML｜｜ invoke>
<｜｜DSML｜｜ invoke name="WebSearchTool">
<｜｜DSML｜｜ parameter name="arguments" string="false">{"query": "境外上市备案", "limit": 8}\</｜｜DSML｜｜ parameter>
\</｜｜DSML｜｜ invoke>
\</｜｜DSML｜｜ calls>"""


def test_dsml_parallel_calls_become_native_function_calls():
    output = normalize_textual_tool_calls(
        [
            Message(
                ASSISTANT,
                DSML_RESPONSE,
                reasoning_content="Need official evidence.",
                name="3wagent",
            )
        ]
    )

    assert output[0].content == "I'll verify the official source."
    assert output[0].reasoning_content == "Need official evidence."
    assert [message.function_call.name for message in output[1:]] == [
        "YamlReadTool",
        "WebSearchTool",
    ]
    assert output[1].function_call.arguments == '{"file_path": "config/output-contract.yaml"}'
    assert output[2].function_call.arguments == '{"query": "境外上市备案", "limit": 8}'
    assert [message.extra["function_id"] for message in output[1:]] == ["1", "2"]


def test_native_function_call_passes_through_unchanged():
    message = Message(
        ASSISTANT,
        "",
        function_call=FunctionCall(name="WebSearchTool", arguments='{"url": "https://x"}'),
    )

    assert normalize_textual_tool_calls([message]) == [message]


def test_legacy_tool_call_tags_are_also_normalized():
    text = '''Checking now.
<tool_call>
{"name": "WebSearchTool", "arguments": {"url": "https://example.com"}}
</tool_call>'''

    output = normalize_textual_tool_calls([Message(ASSISTANT, text)])

    assert output[0].content == "Checking now."
    assert output[1].function_call.name == "WebSearchTool"
    assert output[1].function_call.arguments == '{"url": "https://example.com"}'


def test_reasoning_is_attached_to_tool_call_when_there_is_no_visible_prefix():
    text = (
        '<tool_call>{"name":"WebSearchTool",'
        '"arguments":{"query":"test"}}</tool_call>'
    )

    output = normalize_textual_tool_calls(
        [Message(ASSISTANT, text, reasoning_content="Need to search.")]
    )

    assert output[0].function_call.name == "WebSearchTool"
    assert output[0].reasoning_content == "Need to search."


def test_incomplete_dsml_stays_non_executable_text():
    message = Message(ASSISTANT, '<｜｜DSML｜｜ invoke name="WebSearchTool">')

    assert normalize_textual_tool_calls([message]) == [message]


def test_boundary_only_normalizes_when_tools_are_enabled():
    class FakeBoundary:
        def _call_llm(self, **kwargs):
            yield [Message(ASSISTANT, DSML_RESPONSE)]

    class CompatibleBoundary(ToolCallCompatibilityMixin, FakeBoundary):
        pass

    boundary = CompatibleBoundary()
    without_tools = next(boundary._call_llm(messages=[], functions=[]))
    with_tools = next(
        boundary._call_llm(
            messages=[],
            functions=[{"name": "YamlReadTool"}, {"name": "WebSearchTool"}],
        )
    )

    assert without_tools[0].content == DSML_RESPONSE
    assert with_tools[1].function_call.name == "YamlReadTool"


def test_polluted_native_tool_name_is_repaired_when_arguments_are_valid():
    malformed = Message(
        ASSISTANT,
        "",
        function_call=FunctionCall(
            name='WebSearchTool",\narguments": {"jurisdiction": "CN',
            arguments='{"jurisdiction": "CN", "query": "税收公告"}',
        ),
    )

    output, issue = normalize_native_tool_calls([malformed], {"WebSearchTool"})

    assert issue is None
    assert output[0].function_call.name == "WebSearchTool"
    assert output[0].function_call.arguments == '{"jurisdiction": "CN", "query": "税收公告"}'


def test_native_tool_call_with_lost_arguments_is_rejected():
    malformed = Message(
        ASSISTANT,
        "",
        function_call=FunctionCall(name="WebSearchTool", arguments=""),
    )

    output, issue = normalize_native_tool_calls([malformed], {"WebSearchTool"})

    assert output == []
    assert issue == "invalid_tool_arguments"


def test_long_repeated_reasoning_is_detected_but_normal_answer_is_not():
    repeated = ("I will now write the answer with the available evidence. " * 20).strip()
    assert _has_runaway_repetition(
        [Message(ASSISTANT, "", reasoning_content="\n\n".join([repeated] * 5))]
    )
    assert not _has_runaway_repetition([Message(ASSISTANT, "这是一个简洁且正常的回答。")])


def test_multi_paragraph_planning_cycle_is_detected_independent_of_period():
    cycle = [
        "Actually, I should use a different search approach because the current engine returned no official result.",
        "The question asks for the current policy and effective date, so I still need an authoritative document.",
        "Let me search the official tax website again with shorter keywords and avoid guessing any page URL.",
        "I should not rely on the secondary article until the official source has been located and fetched.",
        "Now I will try another query using the issuing authorities and the affected dividend exemption.",
    ]
    reasoning = "\n\n".join(cycle * 5)

    assert _has_runaway_repetition([Message(ASSISTANT, "", reasoning_content=reasoning)])


def test_boundary_retries_instead_of_executing_malformed_native_call():
    class FakeBoundary:
        calls = 0

        def _call_llm(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield [
                    Message(
                        ASSISTANT,
                        "",
                        function_call=FunctionCall(name="WebSearchTool", arguments="not-json"),
                    )
                ]
            else:
                yield [Message(ASSISTANT, "已改为正常回答。")]

    class CompatibleBoundary(ToolCallCompatibilityMixin, FakeBoundary):
        pass

    boundary = CompatibleBoundary()
    output = list(
        boundary._call_llm(
            messages=[Message(role="user", content="问题")],
            functions=[{"name": "WebSearchTool"}],
        )
    )

    assert boundary.calls == 2
    assert output == [[Message(ASSISTANT, "已改为正常回答。")]]


def test_second_malformed_attempt_ends_with_safe_visible_error():
    class FakeBoundary:
        def _call_llm(self, **kwargs):
            yield [
                Message(
                    ASSISTANT,
                    "",
                    function_call=FunctionCall(name="WebSearchTool", arguments="not-json"),
                )
            ]

    class CompatibleBoundary(ToolCallCompatibilityMixin, FakeBoundary):
        pass

    output = list(
        CompatibleBoundary()._call_llm(
            messages=[Message(role="user", content="问题")],
            functions=[{"name": "WebSearchTool"}],
        )
    )

    assert len(output) == 1
    assert "没有被执行" in output[0][0].content
