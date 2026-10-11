"""Regression tests for query-aware, authority-first web discovery."""

from __future__ import annotations

import json

from src.tools.web_search import WebSearchTool
from src.websearch.protocol import SearchResponse, SearchResult
from src.websearch.registry import infer_official_domains
from src.websearch.relevance import exact_title_search_query, near_duplicate_query, relevance_score


def test_natural_language_with_exact_title_becomes_quoted_compact_query():
    query, strategy = exact_title_search_query(
        "请根据《关于境内居民通过特殊目的公司境外投融资及返程投资外汇管理有关问题的通知》"
        "和汇发〔2014〕37号说明适用对象，不要扩展投资方案"
    )

    assert query == (
        '"关于境内居民通过特殊目的公司境外投融资及返程投资外汇管理有关问题的通知" '
        "汇发〔2014〕37号"
    )
    assert strategy == "exact_title"


def test_exploratory_query_is_not_forced_into_quotes():
    query = "外籍个人 股息红利 个人所得税 近期政策"

    assert exact_title_search_query(query) == (query, "caller_query")


def test_plain_full_document_title_is_quoted_without_model_cooperation():
    title = "关于境外投资者以分配利润直接投资暂不征收预提所得税政策问题的公告"

    assert exact_title_search_query(title) == (f'"{title}"', "exact_title")


def test_tax_registry_aliases_route_to_the_tax_authority():
    assert infer_official_domains(
        "外籍个人 股息红利 个人所得税 政策",
        "CN",
    )[0] == "chinatax.gov.cn"


def test_long_paraphrases_are_detected_but_distinct_short_queries_are_not():
    assert near_duplicate_query(
        "外籍个人从外商投资企业取得股息红利个人所得税政策正式文件执行日期适用对象",
        "外籍个人从外商投资企业取得股息红利个人所得税政策文件执行日期与适用对象",
    )
    assert not near_duplicate_query("测试规则甲", "测试规则乙")


def test_chinese_exact_title_rejects_dictionary_noise():
    query = '"境内企业境外发行证券和上市管理试行办法" 证监会公告 2023年第43号'

    assert relevance_score(query, "境内_百度百科", "术语解释") < 0.1
    assert relevance_score(
        query,
        "【第43号公告】《境内企业境外发行证券和上市管理试行办法》",
        "中国证券监督管理委员会",
    ) == 1.0


def test_known_registry_title_still_searches_for_source_excerpts():
    tool = WebSearchTool()
    calls = []

    class FakeClient:
        def search(self, query, **kwargs):
            calls.append(query)
            return SearchResponse(query=query, engines=["deepseek-official"], results=[
                SearchResult("境内企业境外发行证券和上市管理试行办法",
                             "https://www.csrc.gov.cn/csrc/rule", "适用备案主体",
                             "deepseek-official", "deepseek-official"),
            ])

    tool.client = FakeClient()
    payload = json.loads(tool.call({
        "query": "请根据《境内企业境外发行证券和上市管理试行办法》说明备案主体",
        "jurisdiction": "CN",
    }))
    assert calls == ['"境内企业境外发行证券和上市管理试行办法"']
    assert payload["provider"] == "deepseek-official"
    assert payload["results"][0]["snippet"] == "适用备案主体"


def test_low_quality_results_trigger_one_official_domain_retry(monkeypatch):
    tool = WebSearchTool()
    calls = []
    monkeypatch.setattr(
        "src.tools.web_search.infer_official_domains",
        lambda query, jurisdiction: ["csrc.gov.cn"],
    )

    class FakeClient:
        def search(self, query, **kwargs):
            calls.append((query, kwargs))
            if len(calls) == 1:
                return SearchResponse(
                    query=query,
                    engines=["deepseek-official"],
                    results=[
                        SearchResult("境内_百度百科", "https://baike.baidu.com/item/x", "", "deepseek-official", "web"),
                        SearchResult("中国证券监督管理委员会", "https://www.csrc.gov.cn/", "", "deepseek-official", "web"),
                    ],
                    partial_failures=[
                        {"engine": "deepseek-official", "code": "search_failed", "message": "tool error"},
                    ],
                )
            return SearchResponse(
                query=query,
                engines=["deepseek-official"],
                results=[
                    SearchResult(
                        "全新证券监管测试办法",
                        "https://www.csrc.gov.cn/csrc/new-rule/content.shtml",
                        "证监会发布全新证券监管测试办法",
                        "deepseek-official",
                        "web",
                    )
                ],
            )

    tool.client = FakeClient()
    payload = json.loads(
        tool.call({"query": "《全新证券监管测试办法》 证监会", "jurisdiction": "CN"})
    )

    assert calls[1][0].startswith("site:csrc.gov.cn ")
    assert calls[1][1] == {"limit": 10}
    assert payload["quality"] == "strong"
    assert payload["results"][0]["title"] == "全新证券监管测试办法"
    assert payload["discarded_low_relevance"] == 2
    assert payload["provider"] == "deepseek-official"


def test_nonofficial_survivors_are_labeled_as_leads_not_usable_evidence(monkeypatch):
    tool = WebSearchTool()

    class FakeClient:
        def search(self, query, **kwargs):
            return SearchResponse(
                query=query,
                engines=["deepseek-official"],
                results=[
                    SearchResult(
                        "税务政策二手解读",
                        "https://example.com/commentary",
                        "税务政策二手解读",
                        "deepseek-official",
                        "web",
                    )
                ],
            )

    tool.client = FakeClient()
    payload = json.loads(tool.call({"query": "税务政策二手解读", "jurisdiction": "CN"}))

    assert payload["quality"] == "leads_only"
    assert "not usable evidence" in payload["search_guidance"]


def test_tool_uses_exact_title_query_before_network_search(monkeypatch):
    tool = WebSearchTool()
    calls = []

    class FakeClient:
        def search(self, query, **kwargs):
            calls.append(query)
            return SearchResponse(
                query=query,
                engines=["deepseek-official"],
                results=[
                    SearchResult(
                        "测试监管文件全称",
                        "https://example.com/rule",
                        "测试监管文件全称",
                        "deepseek-official",
                        "web",
                    )
                ],
            )

    tool.client = FakeClient()
    original = "请根据《测试监管文件全称》说明适用对象和执行日期"
    payload = json.loads(tool.call({"query": original}))

    assert calls == ['"测试监管文件全称"']
    assert payload["query"] == '"测试监管文件全称"'
    assert payload["original_query"] == original
    assert payload["query_strategy"] == "exact_title"


def test_irrelevant_government_domain_cannot_hijack_official_retry(monkeypatch):
    monkeypatch.setattr(
        "src.tools.web_search.infer_official_domains",
        lambda query, jurisdiction: ["chinatax.gov.cn"],
    )
    tool = WebSearchTool()
    calls = []

    class FakeClient:
        def search(self, query, **kwargs):
            calls.append(query)
            if len(calls) == 1:
                return SearchResponse(
                    query=query,
                    engines=["deepseek-official"],
                    results=[
                        SearchResult(
                            "全国大学生数学建模竞赛论文",
                            "https://dxs.moe.gov.cn/modeling/",
                            "数学建模优秀论文",
                            "deepseek-official",
                            "web",
                        )
                    ],
                )
            return SearchResponse(query=query, engines=["deepseek-official"], results=[])

    tool.client = FakeClient()
    json.loads(
        tool.call(
            {
                "query": "外籍个人 股息红利 个人所得税 政策",
                "jurisdiction": "CN",
            }
        )
    )

    assert calls[1].startswith("site:chinatax.gov.cn ")
    assert all("dxs.moe.gov.cn" not in query for query in calls)


def test_repeated_long_query_paraphrase_is_stopped_before_network(monkeypatch):
    tool = WebSearchTool()
    calls = []

    class FakeClient:
        def search(self, query, **kwargs):
            calls.append(query)
            return SearchResponse(query=query, engines=["deepseek-official"], results=[])

    tool.client = FakeClient()
    first = json.loads(
        tool.call(
            {
                "query": "外籍个人从外商投资企业取得股息红利个人所得税政策正式文件执行日期适用对象"
            }
        )
    )
    second = json.loads(
        tool.call(
            {
                "query": "外籍个人从外商投资企业取得股息红利个人所得税政策文件执行日期与适用对象"
            }
        )
    )

    assert first["status"] == "ok"
    assert second["error"]["code"] == "redundant_search_query"
    assert "STOP" in second["error"]["message"]
    assert len(calls) == 1
