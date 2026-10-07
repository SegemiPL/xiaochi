"""Terminal frontend tests that do not require a model or network."""

from io import StringIO

from qwen_agent.llm.schema import ASSISTANT, USER, Message
from src.agent.cli import run_cli
from src.agent.main_agent import AgentMode


class FakeAgent:
    name = "3wagent"

    def __init__(self):
        self.mode = AgentMode.NORMAL
        self.current_step = None
        self.calls = []

    def run(self, history):
        self.calls.append(list(history))
        self.current_step = "检索官方来源"
        yield [Message(ASSISTANT, "答", name=self.name)]
        self.current_step = None
        yield [Message(ASSISTANT, "答案", name=self.name)]


def test_cli_only_displays_completed_answers_and_preserves_multi_turn_history():
    agent = FakeAgent()
    output = StringIO()
    errors = StringIO()

    run_cli(
        agent,
        input_stream=StringIO("第一个问题\n第二个问题\n/exit\n"),
        output_stream=output,
        error_stream=errors,
    )

    assert output.getvalue().count("小弛> 答案") == 2
    assert "检索官方来源" not in errors.getvalue()
    assert "小弛> 答\n" not in output.getvalue()
    assert output.getvalue().count("以上内容由 AI 生成") == 2
    assert len(agent.calls) == 2
    assert [message.role for message in agent.calls[1]] == [USER, ASSISTANT, USER]
    assert agent.calls[1][-1].content == "第二个问题"


def test_cli_clear_starts_a_fresh_history():
    agent = FakeAgent()
    output = StringIO()

    run_cli(
        agent,
        input_stream=StringIO("旧问题\n/clear\n新问题\n/quit\n"),
        output_stream=output,
        error_stream=StringIO(),
    )

    assert "对话已清空" in output.getvalue()
    assert len(agent.calls) == 2
    assert len(agent.calls[1]) == 1
    assert agent.calls[1][0].content == "新问题"


def test_cli_does_not_print_subagent_transcript_as_final_answer():
    class WorkflowAgent(FakeAgent):
        def run(self, history):
            yield [Message(ASSISTANT, "内部检索结果", name="rag_subagent")]
            yield [
                Message(ASSISTANT, "内部检索结果", name="rag_subagent"),
                Message(ASSISTANT, "用户可见结论", name=self.name),
            ]

    output = StringIO()
    run_cli(
        WorkflowAgent(),
        input_stream=StringIO("问题\n/exit\n"),
        output_stream=output,
        error_stream=StringIO(),
    )

    assert "用户可见结论" in output.getvalue()
    assert "内部检索结果" not in output.getvalue()


def test_cli_recovers_after_a_failed_turn():
    class FlakyAgent(FakeAgent):
        def run(self, history):
            self.calls.append(list(history))
            if len(self.calls) == 1:
                raise RuntimeError("temporary failure")
            yield [Message(ASSISTANT, "恢复成功", name=self.name)]

    agent = FlakyAgent()
    output = StringIO()
    errors = StringIO()
    run_cli(
        agent,
        input_stream=StringIO("失败问题\n重试问题\n/exit\n"),
        output_stream=output,
        error_stream=errors,
    )

    assert "暂时无法完成查询" in errors.getvalue()
    assert "temporary failure" not in errors.getvalue()
    assert "恢复成功" in output.getvalue()
    assert len(agent.calls[1]) == 1
    assert agent.calls[1][0].content == "重试问题"
