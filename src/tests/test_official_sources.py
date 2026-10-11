"""Policy evidence acquisition, fallback and boundaries, with no live network."""

import json

import pytest
from src.websearch.sources import MAX_HTML_BYTES, OfficialSourceReader

URL = "https://szs.mof.gov.cn/policy.htm"
DOMAINS = ["mof.gov.cn", "chinatax.gov.cn"]
POLICY = (
    "财政部 税务总局公告2026年第27号\n"
    "一、外籍个人从外商投资企业取得的股息红利所得，按照“利息、股息、红利所得”缴纳个人所得税，适用20%税率。\n"
    "三、本公告自2026年9月1日起执行，财税字〔1994〕20号第二条第（八）项同时废止。"
)


def html(container='class="TRS_Editor"', encoding="utf-8"):
    return (
        '<html><head><meta name="ArticleTitle" content="政策公告"></head>'
        "<nav>导航不是政策</nav><div " + container + "><style>do not include</style>"
        "<script>ignore instructions</script><p>"
        + POLICY.replace("\n", "</p><p>")
        + "</p></div><footer>网站声明</footer></html>"
    ).encode(encoding)


@pytest.mark.parametrize("container", ['class="TRS_Editor"', 'class="my_doccontent"', 'id="zoom"'])
def test_official_layouts_return_actual_clauses_without_scripts_or_navigation(container):
    reader = OfficialSourceReader(
        transport=lambda *args: (200, {"Content-Type": "text/html"}, html(container))
    )
    result = reader.read(URL, DOMAINS)
    assert result["source_text"] == POLICY
    assert result["source_title"] == "政策公告"
    assert result["source_url"] == URL
    assert result["source_read_at"] and len(result["source_sha256"]) == 64
    assert result["source_truncated"] is False


def test_chinese_charset_and_read_cache_do_not_repeat_requests():
    calls = []

    def transport(request, timeout):
        calls.append(request)
        assert not any(key.lower() in {"authorization", "x-api-key"} for key in request.headers)
        return 200, {"Content-Type": "text/html; charset=gb2312"}, html(encoding="gb2312")

    reader = OfficialSourceReader(transport=transport)
    assert reader.read(URL, DOMAINS)["source_text"] == POLICY
    assert reader.read(URL, DOMAINS)["source_text"] == POLICY
    assert len(calls) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://mof.gov.cn.evil.test/fake",
        "file:///etc/passwd",
        "https://user:secret@szs.mof.gov.cn/policy",
        "http://127.0.0.1/policy",
        "https://szs.mof.gov.cn:8000/policy",
    ],
)
def test_untrusted_search_url_cannot_trigger_official_reader(url):
    calls = []
    reader = OfficialSourceReader(transport=lambda *args: calls.append(args))
    assert reader.read(url, DOMAINS)["source_status"] == "unavailable"
    assert calls == []


def test_redirect_outside_official_domains_is_not_followed():
    calls = []

    def transport(request, timeout):
        calls.append(request.full_url)
        return 302, {"Location": "http://127.0.0.1/internal"}, b""

    result = OfficialSourceReader(transport=transport).read(URL, DOMAINS)
    assert result["source_error"] == "url_outside_official_domains"
    assert calls == [URL]


@pytest.mark.parametrize(
    "response, error",
    [
        ((403, {}, b""), "http_403"),
        ((200, {"content-type": "application/pdf"}, b"%PDF"), "unsupported_content_type"),
        (
            (200, {"content-type": "text/html"}, b"<h1>A title</h1><nav>No article text</nav>"),
            "article_container_not_found",
        ),
        ((200, {"content-type": "text/html"}, b"x" * (MAX_HTML_BYTES + 1)), "page_too_large"),
    ],
)
def test_missing_or_unsupported_body_is_never_reported_as_policy_text(response, error):
    result = OfficialSourceReader(transport=lambda *args: response).read(URL, DOMAINS)
    assert result["source_error"] == error
    assert "source_text" not in result


def test_enrichment_tries_other_official_pages_after_first_batch_fails():
    urls = [f"https://www.chinatax.gov.cn/policy{i}" for i in range(4)]
    results = [{"url": url, "is_official": True} for url in urls]

    def transport(request, timeout):
        if request.full_url != urls[-1]:
            return 403, {}, b""
        return 200, {"content-type": "text/html"}, html()

    OfficialSourceReader(transport=transport).enrich(results, DOMAINS)
    assert results[-1]["source_text"] == POLICY
    assert all(item["source_error"] == "http_403" for item in results[:3])


def test_deepseek_url_only_result_becomes_evidence_only_after_official_read():
    from src.tools.web_search import WebSearchTool
    from src.websearch.protocol import SearchResponse, SearchResult

    class Search:
        def search(self, query, **kwargs):
            return SearchResponse(
                query=query,
                engines=["deepseek-official"],
                results=[
                    SearchResult("外籍个人股息红利政策公告", URL, "", "deepseek-official", "web")
                ],
            )

    tool = WebSearchTool()
    tool.client = Search()
    tool.source_reader = OfficialSourceReader(
        transport=lambda *args: (200, {"content-type": "text/html"}, html())
    )
    result = json.loads(tool.call({"query": "外籍个人 股息红利 政策", "jurisdiction": "CN"}))
    assert result["quality"] == "strong"
    assert result["official_text_results"] == 1
    assert result["official_excerpt_results"] == 0
    assert result["results"][0]["source_text"] == POLICY
    assert result["results"][0]["snippet"] == ""
