"""Final-answer-only terminal frontend for Xiaochi."""

from __future__ import annotations

import sys
from typing import TextIO

from qwen_agent.llm.schema import USER, Message

from src.agent.main_agent import AgentMode, MainAgent
from src.agent.public_answer import completed_answer
from src.config.llm import load_llm_config
from src.config.product import AGENT_NAME

EXIT_COMMANDS = {"/exit", "/quit"}


def build_cli_agent(model_name=None, provider=None, config_path=None) -> MainAgent:
    """Create the same agent used by the Web app without importing its server."""
    return MainAgent(
        llm=load_llm_config(
            model_name=model_name,
            provider=provider,
            config_path=config_path,
        )
    )


def run_cli(
    agent: MainAgent,
    *,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
    error_stream: TextIO = sys.stderr,
) -> None:
    """Run a multi-turn terminal conversation until EOF or ``/exit``."""
    history: list[Message] = []
    _write(
        output_stream,
        "小弛 CLI\n命令：/clear 清空对话，/exit 或 /quit 退出。\n",
    )

    while True:
        _write(output_stream, "\n你> ")
        line = input_stream.readline()
        if line == "":
            _write(output_stream, "\n")
            return

        question = line.strip()
        if not question:
            continue
        if question.lower() in EXIT_COMMANDS:
            return
        if question.lower() == "/clear":
            history.clear()
            _reset_agent_state(agent)
            _write(output_stream, "对话已清空。\n")
            continue

        history.append(Message(USER, question))
        responses: list[Message] = []
        try:
            for responses in agent.run(history):
                pass
        except KeyboardInterrupt:
            _reset_agent_state(agent)
            history.pop()
            _write(error_stream, "\n本轮已取消。\n")
            continue
        except Exception:  # noqa: BLE001 - keep the REPL usable after one failed turn
            _reset_agent_state(agent)
            history.pop()
            _write(error_stream, "\n暂时无法完成查询，请稍后重试。\n")
            continue

        if responses:
            history.extend(responses)
        answer = completed_answer(responses, getattr(agent, 'name', AGENT_NAME))
        _write(output_stream, f"小弛> {answer}\n")


def run_cli_3wagent(model_name=None, provider=None, config_path=None) -> None:
    run_cli(build_cli_agent(model_name, provider, config_path))


def _reset_agent_state(agent: MainAgent) -> None:
    agent.mode = AgentMode.NORMAL
    agent.current_step = None


def _write(stream: TextIO, text: str) -> None:
    stream.write(text)
    stream.flush()
