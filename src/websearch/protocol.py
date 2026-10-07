"""Stable internal response types for DeepSeek web search."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    engine: str
    source: str
    published_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if self.published_at is None:
            result.pop("published_at")
        return result


@dataclass(frozen=True)
class SearchResponse:
    query: str
    engines: list[str]
    results: list[SearchResult]
    partial_failures: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "engines": self.engines,
            "total_results": len(self.results),
            "results": [item.to_dict() for item in self.results],
            "partial_failures": self.partial_failures,
            "truncated": self.truncated,
        }
