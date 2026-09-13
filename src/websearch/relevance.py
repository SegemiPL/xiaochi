"""Lightweight, topic-independent relevance scoring for search discovery."""

from __future__ import annotations

import re
import unicodedata

_BOOK_TITLE_RE = re.compile(r"《([^》]{2,})》")
_QUOTED_RE = re.compile(r"[\"“”']([^\"“”']{3,})[\"“”']")
_SITE_RE = re.compile(r"\bsite\s*:\s*[^\s]+", re.IGNORECASE)
_ASCII_WORD_RE = re.compile(r"[a-z0-9][a-z0-9._-]+", re.IGNORECASE)
_CJK_RUN_RE = re.compile(r"[\u3400-\u9fff]{2,}")
_DOCUMENT_NUMBER_RE = re.compile(
    r"(?:[\u3400-\u9fff]{1,10})?[〔\[]\d{4}[〕\]]\s*(?:第)?\d+号?",
    re.IGNORECASE,
)
_PLAIN_DOCUMENT_TITLE_RE = re.compile(
    r"^(?:关于|中华人民共和国)[^\n]{8,100}(?:公告|通知|办法|条例|规定|决定|意见|指引|细则)$"
)


def normalize_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in normalized if char.isalnum())


def strip_site_operators(query: str) -> str:
    return re.sub(r"\s+", " ", _SITE_RE.sub(" ", query)).strip()


def exact_title_search_query(query: str) -> tuple[str, str]:
    """Turn an explicit Chinese book-title citation into a compact exact query.

    Users commonly embed an exact regulation title inside a long natural-language
    request. Sending that entire sentence to Chinese Bing produces morphological
    noise; the title plus an optional document number is the better discovery key.
    Already quoted queries are preserved because the caller has made an explicit
    search-strategy choice.
    """

    original = query.strip()
    clean = strip_site_operators(original)
    titles = _BOOK_TITLE_RE.findall(clean)
    if not titles and _PLAIN_DOCUMENT_TITLE_RE.fullmatch(clean):
        titles = [clean]
    if not titles or _QUOTED_RE.search(clean):
        return original, "caller_query"
    title = titles[0].strip()
    if len(normalize_search_text(title)) < 8:
        return original, "caller_query"
    numbers = list(
        dict.fromkeys(
            match.group(0).strip().lstrip("和及与")
            for match in _DOCUMENT_NUMBER_RE.finditer(clean)
        )
    )
    suffix = f" {' '.join(numbers)}" if numbers else ""
    return f'"{title}"{suffix}', "exact_title"


def near_duplicate_query(left: str, right: str, *, threshold: float = 0.76) -> bool:
    """Detect repeated long-query paraphrases within one agent run."""

    left_text = normalize_search_text(strip_site_operators(left))
    right_text = normalize_search_text(strip_site_operators(right))
    if left_text == right_text:
        return True
    if min(len(left_text), len(right_text)) < 12:
        return False
    left_grams = _ngrams(left_text, 2)
    right_grams = _ngrams(right_text, 2)
    union = left_grams | right_grams
    return bool(union) and len(left_grams & right_grams) / len(union) >= threshold


def query_phrases(query: str) -> list[str]:
    """Extract useful fragments without requiring a Chinese tokenizer."""

    clean = strip_site_operators(query)
    phrases: list[str] = []
    phrases.extend(_BOOK_TITLE_RE.findall(clean))
    phrases.extend(_QUOTED_RE.findall(clean))
    unquoted = _BOOK_TITLE_RE.sub(" ", _QUOTED_RE.sub(" ", clean))
    phrases.extend(_CJK_RUN_RE.findall(unquoted))
    phrases.extend(_ASCII_WORD_RE.findall(clean))

    unique: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        normalized = normalize_search_text(phrase)
        if len(normalized) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def relevance_score(query: str, title: str, snippet: str = "") -> float:
    """Return a stable 0..1 discovery score for one result."""

    title_text = normalize_search_text(title)
    body_text = normalize_search_text(f"{title} {snippet}")
    if not body_text:
        return 0.0

    explicit = [
        normalize_search_text(value)
        for value in (*_BOOK_TITLE_RE.findall(query), *_QUOTED_RE.findall(query))
        if len(normalize_search_text(value)) >= 3
    ]
    if any(phrase in title_text for phrase in explicit):
        return 1.0
    if any(phrase in body_text for phrase in explicit):
        return 0.92

    terms = query_phrases(query)
    if not terms:
        query_text = normalize_search_text(strip_site_operators(query))
        if not query_text:
            return 0.0
        return 1.0 if query_text in body_text else _ngram_overlap(query_text, title_text)

    weights = [min(len(term), 24) for term in terms]
    covered = sum(weight for term, weight in zip(terms, weights) if term in body_text)
    coverage = covered / max(1, sum(weights))
    partial = _ngram_overlap(max(terms, key=len), title_text)
    return round(min(1.0, 0.78 * coverage + 0.22 * partial), 4)


def _ngram_overlap(left: str, right: str, size: int = 2) -> float:
    if not left or not right:
        return 0.0
    if len(left) < size or len(right) < size:
        return 1.0 if left == right else 0.0
    left_grams = _ngrams(left, size)
    right_grams = _ngrams(right, size)
    return len(left_grams & right_grams) / max(1, len(left_grams))


def _ngrams(value: str, size: int) -> set[str]:
    return {value[index : index + size] for index in range(len(value) - size + 1)}
