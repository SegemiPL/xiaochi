"""Load the repository's private .env once, independently of the working directory."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ENV_PATH = Path(__file__).resolve().parents[2] / '.env'


def load_project_env(path: Path | None = None) -> bool:
    """Existing process variables take precedence; values are never printed."""
    return load_dotenv(path or PROJECT_ENV_PATH, override=False, interpolate=False)


def get_env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def environment() -> dict[str, str]:
    return dict(os.environ)


load_project_env()
