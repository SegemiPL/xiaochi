#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
exec src/.venv/bin/python -c '
import os, sys
from pathlib import Path
from src.config.env import load_project_env
load_project_env()
if not os.getenv("DEEPSEEK_API_KEY"):
    specified = os.getenv("DEEPSEEK_API_KEY_FILE")
    key = Path(specified or ".local/deepseek-api-key.txt").expanduser()
    if not specified and not key.is_file():
        key = Path("../one2one-education/.local/deepseek-api-key.txt")
    if key.is_file():
        os.environ["DEEPSEEK_API_KEY"] = key.read_text().strip()
os.execv(sys.executable, [sys.executable, "-m", "src.main", "--port", os.getenv("XIAOCHI_PORT", "7860"), *sys.argv[1:]])
' "$@"
