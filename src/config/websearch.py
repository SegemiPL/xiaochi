"""Configuration for DeepSeek native web search; no local daemon required."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


def _env_int(
    environ: dict[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = environ.get(name)
    try:
        value = int(raw) if raw is not None else default
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


@dataclass(frozen=True)
class DeepSeekSearchSettings:
    """Messages API settings matching Harness's web-search-deepseek provider.

    Search uses DEEPSEEK_API_KEY, independently of the main agent's provider.
    Keys are resolved per request and never stored in these settings.
    """

    base_url: str = "https://api.deepseek.com/anthropic/v1"
    model: str = "deepseek-v4-flash"
    api_version: str = "2023-06-01"
    max_tokens: int = 4096
    max_uses: int = 5
    timeout_seconds: int = 120
    max_results: int = 10

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> DeepSeekSearchSettings:
        env = dict(os.environ if environ is None else environ)
        base_url = env.get("DEEPSEEK_SEARCH_BASE_URL", cls.base_url).strip().rstrip("/")
        parsed = urlparse(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("DEEPSEEK_SEARCH_BASE_URL must be an HTTPS base URL without credentials")
        model = env.get("DEEPSEEK_SEARCH_MODEL", cls.model).strip()
        if not model:
            raise ValueError("DEEPSEEK_SEARCH_MODEL must not be empty")
        return cls(
            base_url=base_url,
            max_results=_env_int(
                env, "WEBSEARCH_MAX_RESULTS", cls.max_results, minimum=1, maximum=50
            ),
            model=model,
            max_tokens=_env_int(
                env, "DEEPSEEK_SEARCH_MAX_TOKENS", cls.max_tokens, minimum=1, maximum=32768
            ),
            max_uses=_env_int(
                env, "DEEPSEEK_SEARCH_MAX_USES", cls.max_uses, minimum=1, maximum=5
            ),
            timeout_seconds=_env_int(
                env, "DEEPSEEK_SEARCH_TIMEOUT_SECONDS", cls.timeout_seconds,
                minimum=1, maximum=600,
            ),
        )
