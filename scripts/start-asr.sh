#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
voice_repo="$(python3 -c 'from src.voice.config import settings; from pathlib import Path; print(Path(settings()["asr_repo"]).expanduser().resolve())')"
voice_python="${VOICE_ASR_PYTHON:-$voice_repo/.venv-voice/bin/python}"
if [[ ! -x "$voice_python" ]]; then
  echo '未找到已有的语音 Python 环境，请配置 VOICE_ASR_REPO 或 VOICE_ASR_PYTHON。' >&2
  exit 1
fi
exec "$voice_python" -m src.voice.asr_service
