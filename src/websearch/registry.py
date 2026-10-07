"""Query-aware access to curated source registries."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from src.tools.common import PROJECT_ROOT
from src.websearch.relevance import relevance_score


def infer_official_domains(query: str, jurisdiction: str | None, *, limit: int = 2) -> list[str]:
    """Infer likely authority hosts from related registry entries."""

    ranked: list[tuple[float, str]] = []
    for entry in _load_registry_entries(jurisdiction):
        hostname = (urlparse(str(entry.get("url") or "")).hostname or "").lower()
        if not hostname:
            continue
        title = str(entry.get("title") or "")
        context = " ".join(
            (
                str(entry.get('authority') or ''),
                str(entry.get('notes') or ''),
                " ".join(str(item) for item in entry.get("aliases") or []),
                " ".join(str(item) for item in entry.get("keywords") or []),
            )
        )
        score = relevance_score(query, title, context)
        if score >= 0.2:
            ranked.append((score, hostname.removeprefix("www.")))
    ranked.sort(reverse=True)
    domains: list[str] = []
    for _, domain in ranked:
        if domain not in domains:
            domains.append(domain)
        if len(domains) >= limit:
            break
    return domains


def _load_registry_entries(
    jurisdiction: str | None, *, registry_path: Path | None = None
) -> list[dict[str, Any]]:
    if not jurisdiction and registry_path is None:
        return []
    path = registry_path or PROJECT_ROOT / "sources" / f"{jurisdiction.lower()}.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return []
    sources = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(sources, list):
        return []
    return [entry for entry in sources if isinstance(entry, dict)]
