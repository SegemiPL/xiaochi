import os

# Raise qwen-agent's per-run LLM call cap BEFORE any qwen_agent import reads
# it. The default (20) silently truncates search-heavy sub-agents mid-loop.
os.environ.setdefault('QWEN_AGENT_MAX_LLM_CALL_PER_RUN', '40')

import argparse

from qwen_agent.log import logger

from src.agent.main_agent import run_3wagent


def parse_args():
    parser = argparse.ArgumentParser(description = "小弛 · 税务工作辅助助手")
    parser.add_argument("-d", "--DEBUG", default=False, action="store_true", help="DEBUG Mode")
    parser.add_argument(
        "--cli",
        action="store_true",
        help="start an interactive terminal session instead of the Web app",
    )
    parser.add_argument(
        "-p", "--provider", help="LLM provider from the selected LLM config"
    )
    parser.add_argument("-m", "--model", default=None, help="override the provider's model name")
    parser.add_argument(
        "--llm-config",
        default=None,
        help="path to an alternative provider YAML (default: src/config/llm.yaml)",
    )

    parser.add_argument("--host", default="127.0.0.1", help="Web server bind address")
    parser.add_argument("--port", default=8000, type=int, help="Web server port")
    return parser.parse_args()

def main():
    args = parse_args()

    # DEBUG Mode; the per-run log file is attached at the start of each run
    if args.DEBUG :
        logger.setLevel('DEBUG')

    runner = run_3wagent
    if args.cli:
        # Keep terminal-only use independent of the Web server.
        from src.agent.cli import run_cli_3wagent

        runner = run_cli_3wagent
    options = {} if args.cli else {"host": args.host, "port": args.port}
    runner(
        model_name=args.model,
        provider=args.provider,
        config_path=args.llm_config,
        **options,
    )


if __name__ == "__main__":
    main()
