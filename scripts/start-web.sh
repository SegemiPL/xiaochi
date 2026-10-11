#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

# Keep credentials in the backend environment, never in command-line arguments.
if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  key_file="${DEEPSEEK_API_KEY_FILE:-.local/deepseek-api-key.txt}"
  if [[ -z "${DEEPSEEK_API_KEY_FILE:-}" && ! -f "$key_file" ]]; then
    key_file="../one2one-education/.local/deepseek-api-key.txt"
  fi
  if [[ -f "$key_file" ]]; then
    DEEPSEEK_API_KEY="$(< "$key_file")"
    export DEEPSEEK_API_KEY
  fi
fi

exec src/.venv/bin/python -m src.main "$@"
