"""DeepSeek native search using the same Messages protocol as DeepSeek Harness.

Protocol reference:
https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/web/web-search-deepseek

The generated answer is deliberately ignored. Only structured search results
and citation excerpts become discovery leads for the agent's evidence pipeline.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from src.agent.progress import progress_stage
from src.config.env import get_env
from src.config.websearch import DeepSeekSearchSettings
from src.websearch.protocol import SearchResponse, SearchResult

MAX_RESPONSE_BYTES = 4 * 1024 * 1024
PROVIDER = "deepseek-official"
Transport = Callable[[Request, float], tuple[int, bytes]]


class DeepSeekSearchError(RuntimeError):
    """A structured DeepSeek search transport or protocol error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code
        self.hint = hint

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "status_code": self.status_code,
            "hint": self.hint,
        }


class _NoRedirects(HTTPRedirectHandler):
    """Never forward API credentials to a redirect destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DeepSeekSearchClient:
    def __init__(
        self,
        settings: DeepSeekSearchSettings | None = None,
        *,
        transport: Transport | None = None,
        record_request: Callable[[dict], None] | None = None,
    ):
        self.settings = settings or DeepSeekSearchSettings.from_env()
        self._opener = build_opener(_NoRedirects())
        self._transport = transport or self._default_transport
        self._record_request = record_request

    def search(self, query: str, *, limit: int = 10) -> SearchResponse:
        query = query.strip()
        if not query:
            raise DeepSeekSearchError("invalid_arguments", "search query must not be empty")
        if not isinstance(limit, int) or limit < 1:
            raise DeepSeekSearchError("invalid_arguments", "search limit must be a positive integer")
        api_key = get_env("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise DeepSeekSearchError(
                "missing_api_key", "Set DEEPSEEK_API_KEY to use DeepSeek native web search"
            )
        endpoint = f"{self.settings.base_url}/messages"
        body = {
            "model": self.settings.model,
            "max_tokens": self.settings.max_tokens,
            "output_config": {"effort": self.settings.reasoning_effort},
            "messages": [{
                "role": "user",
                "content": [{"type": "text", "text": f"Perform a web search for the query: {query}"}],
            }],
            "tools": [{
                "type": "web_search_20250305", "name": "web_search",
                "max_uses": self.settings.max_uses,
            }],
        }
        if self._record_request is not None:
            self._record_request({
                "endpoint": endpoint, "api_version": self.settings.api_version, "body": body,
            })
        request = Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "x-api-key": api_key,
                "Authorization": f"Bearer {api_key}",
                "anthropic-version": self.settings.api_version,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "3wagent-deepseek-search/0.1",
            },
            method="POST",
        )
        try:
            with progress_stage('searching'):
                status, raw = self._transport(request, self.settings.timeout_seconds)
        except (OSError, URLError, TimeoutError) as exc:
            # Do not echo transport exceptions: they can contain request headers.
            raise DeepSeekSearchError(
                "search_unavailable", f"DeepSeek search transport failed ({type(exc).__name__})",
                retryable=True,
            ) from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise DeepSeekSearchError("response_too_large", "DeepSeek search response exceeds size limit")
        if not 200 <= status < 300:
            # Provider response bodies are untrusted and may echo credentials.
            raise DeepSeekSearchError(
                "search_api_error", f"DeepSeek search returned HTTP {status}",
                status_code=status, retryable=status == 429 or status >= 500,
            )
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeError):
            raise DeepSeekSearchError("invalid_response", "DeepSeek search returned invalid JSON") from None
        return parse_search_response(payload, query=query, limit=min(limit, 50))

    def _default_transport(self, request: Request, timeout: float) -> tuple[int, bytes]:
        try:
            with self._opener.open(request, timeout=timeout) as response:
                return response.status, response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            with exc:
                return exc.code, exc.read(MAX_RESPONSE_BYTES + 1)


def parse_search_response(payload: object, *, query: str, limit: int) -> SearchResponse:
    if not isinstance(payload, dict) or not isinstance(payload.get("content"), list):
        raise DeepSeekSearchError("invalid_response", "DeepSeek search response has no content blocks")
    blocks = payload["content"]
    result_blocks = [
        block for block in blocks
        if isinstance(block, dict) and block.get("type") == "web_search_tool_result"
    ]
    if not result_blocks:
        raise DeepSeekSearchError(
            "native_search_not_triggered",
            "DeepSeek returned no web_search_tool_result blocks; native search was not confirmed. "
            "Check the configured search endpoint and model",
        )
    snippets: dict[str, list[str]] = {}
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        citations = block.get("citations")
        for cite in citations if isinstance(citations, list) else []:
            if not isinstance(cite, dict):
                continue
            url, text = cite.get("url"), cite.get("cited_text")
            if isinstance(url, str) and isinstance(text, str) and text.strip():
                excerpts = snippets.setdefault(url, [])
                if text not in excerpts:
                    excerpts.append(text)

    results: list[SearchResult] = []
    seen: set[str] = set()
    failures: list[dict] = []
    for block in result_blocks:
        items = block.get("content")
        if isinstance(items, dict) and items.get("type") == "web_search_tool_result_error":
            failures.append({
                "engine": PROVIDER, "code": str(items.get("error_code") or "search_failed"),
                "message": "DeepSeek native search returned a tool error",
            })
            continue
        if not isinstance(items, list):
            raise DeepSeekSearchError("invalid_response", "Invalid DeepSeek search result block")
        for item in items:
            if not isinstance(item, dict) or item.get("type") != "web_search_result":
                continue
            url = item.get("url")
            if not isinstance(url, str) or url in seen:
                continue
            try:
                parsed = urlparse(url)
                valid_url = (
                    parsed.scheme in {"http", "https"} and parsed.hostname
                    and parsed.username is None and parsed.password is None
                )
            except ValueError:
                valid_url = False
            if not valid_url:
                continue
            seen.add(url)
            results.append(SearchResult(
                title=item.get("title") if isinstance(item.get("title"), str) else "",
                url=url, snippet="\n".join(snippets.get(url, [])),
                engine=PROVIDER, source=PROVIDER,
                published_at=item.get("page_age") if isinstance(item.get("page_age"), str) else None,
            ))
    if failures and not results:
        raise DeepSeekSearchError("native_search_failed", "DeepSeek native search returned a tool error")
    return SearchResponse(
        query=query, engines=[PROVIDER], results=results[:limit], partial_failures=failures,
        truncated=len(results) > limit or payload.get("stop_reason") == "max_tokens",
    )
