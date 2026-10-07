"""Read official HTML articles discovered by DeepSeek, without API credentials."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
import time
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from threading import Lock
from typing import ClassVar
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener

from src.agent.progress import progress_stage
from src.websearch.deepseek import _NoRedirects
from src.websearch.policy import is_official_url

MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 16000
Transport = Callable[[Request, float], tuple[int, dict[str, str], bytes]]
_CACHE: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_CACHE_LOCK = Lock()


class SourceReadError(RuntimeError):
    """A page could not be safely retrieved or identified as an article."""


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list = field(default_factory=list)


class _ArticleParser(HTMLParser):
    """Keep article containers and discard scripts, styles and navigation."""

    VOID: ClassVar[set[str]] = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "wbr",
    }
    SKIP: ClassVar[set[str]] = {
        "script",
        "style",
        "nav",
        "footer",
        "form",
        "button",
        "iframe",
        "svg",
        "aside",
        "noscript",
        "head",
    }
    CONTAINERS: ClassVar[set[str]] = {
        "trs_editor",
        "my_doccontent",
        "article-content",
        "article_content",
        "content-article",
        "content_article",
        "xxgk_content",
        "zoom",
        "fontzoom",
        "articlecontent",
        "contenttext",
        "ucap-content",
        "contentbody",
    }
    BLOCK: ClassVar[set[str]] = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "section", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self.stack = [self.root]
        self.nodes = []
        self.metadata = {}

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, {key: value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        self.nodes.append(node)
        if tag == "meta":
            self.metadata[node.attrs.get("name", "").lower()] = node.attrs.get("content", "")
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    def text(self, node):
        if isinstance(node, str):
            return node
        if node.tag in self.SKIP:
            return ""
        value = "".join(self.text(child) for child in node.children)
        return "\n" + value + "\n" if node.tag in self.BLOCK else value

    def article(self):
        candidates = [
            node
            for node in self.nodes
            if (
                node.tag == "article"
                or self.CONTAINERS.intersection(node.attrs.get("class", "").lower().split())
                or node.attrs.get("id", "").lower() in self.CONTAINERS
            )
        ]
        if not candidates:
            raise SourceReadError("article_container_not_found")
        raw = max((self.text(node) for node in candidates), key=len)
        text = "\n".join(line for part in raw.splitlines() if (line := " ".join(part.split())))
        if len(text) < 60:
            raise SourceReadError("article_text_missing")
        title = self.metadata.get("articletitle") or self.metadata.get("doctitle")
        if not title:
            headings = [node for node in self.nodes if node.tag in {"h1", "h2"}]
            title = next(
                (self.text(node).strip() for node in headings if self.text(node).strip()), ""
            )
        return title, text


def _validate_url(url: str, domains: list[str]) -> None:
    try:
        parts = urlsplit(url)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.port not in {None, 80, 443}
            or not is_official_url(url, domains)
        ):
            raise SourceReadError("url_outside_official_domains")
        try:
            address = ipaddress.ip_address(parts.hostname)
        except ValueError:
            return
        if not address.is_global:
            raise SourceReadError("non_public_address")
    except ValueError as exc:
        raise SourceReadError("invalid_url") from exc


class OfficialSourceReader:
    def __init__(self, *, transport: Transport | None = None):
        self._transport = transport or self._default_transport

    @staticmethod
    def _default_transport(request: Request, timeout: float):
        hostname = urlsplit(request.full_url).hostname
        addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        if not addresses or any(
            not ipaddress.ip_address(item[4][0]).is_global for item in addresses
        ):
            raise SourceReadError("non_public_address")
        opener = build_opener(_NoRedirects())
        try:
            response = opener.open(request, timeout=timeout)
        except HTTPError as exc:
            response = exc
        with response:
            body = response.read(MAX_HTML_BYTES + 1)
            if len(body) > MAX_HTML_BYTES:
                raise SourceReadError("page_too_large")
            return response.status, dict(response.headers.items()), body

    def read(self, url: str, domains: list[str]) -> dict:
        try:
            _validate_url(url, domains)
            with _CACHE_LOCK:
                cached = _CACHE.get(url)
                if cached and time.monotonic() - cached[0] < 900:
                    _validate_url(cached[1]["source_url"], domains)
                    _CACHE.move_to_end(url)
                    return dict(cached[1])
            current = url
            for _ in range(4):
                _validate_url(current, domains)
                request = Request(
                    current,
                    headers={
                        "User-Agent": "Xiaochi/1.0 (official policy reader)",
                        "Accept": "text/html,application/xhtml+xml",
                    },
                )
                status, headers, body = self._transport(request, 12.0)
                headers = {key.lower(): value for key, value in headers.items()}
                if status in {301, 302, 303, 307, 308}:
                    current = urljoin(current, headers.get("location", ""))
                    continue
                if status != 200:
                    raise SourceReadError(f"http_{status}")
                if len(body) > MAX_HTML_BYTES:
                    raise SourceReadError("page_too_large")
                if "html" not in headers.get("content-type", "").lower():
                    raise SourceReadError("unsupported_content_type")
                encoding_match = re.search(
                    r'charset\s*=\s*["\x27]?([\w-]+)',
                    headers.get("content-type", "")
                    + " "
                    + body[:4096].decode("ascii", errors="ignore"),
                    re.IGNORECASE,
                )
                encoding = encoding_match[1] if encoding_match else "utf-8"
                try:
                    html = body.decode(encoding)
                except (UnicodeError, LookupError):
                    html = body.decode("gb18030", errors="replace")
                parser = _ArticleParser()
                parser.feed(html)
                title, text = parser.article()
                result = {
                    "source_status": "read",
                    "source_url": current,
                    "source_title": title,
                    "source_text": text[:MAX_TEXT_CHARS],
                    "source_truncated": len(text) > MAX_TEXT_CHARS,
                    "source_read_at": datetime.now(UTC).isoformat(),
                    "source_sha256": hashlib.sha256(body).hexdigest(),
                }
                with _CACHE_LOCK:
                    _CACHE[url] = (time.monotonic(), result)
                    while len(_CACHE) > 128:
                        _CACHE.popitem(last=False)
                return dict(result)
            raise SourceReadError("too_many_redirects")
        except (SourceReadError, URLError, OSError, ValueError) as exc:
            code = str(exc) if isinstance(exc, SourceReadError) else type(exc).__name__
            return {"source_status": "unavailable", "source_error": code}

    def enrich(self, results: list[dict], domains: list[str]) -> None:
        """Read up to three ranked official candidates, retaining failed-page evidence."""
        targets = [item for item in results if item["is_official"]]
        if not targets:
            return
        with progress_stage("reading"), ThreadPoolExecutor(max_workers=3) as pool:
            for start in range(0, len(targets), 3):
                batch = targets[start : start + 3]
                responses = list(pool.map(lambda item: self.read(item["url"], domains), batch))
                for item, response in zip(batch, responses, strict=True):
                    item.update(response)
                if any(response.get("source_text") for response in responses):
                    break
