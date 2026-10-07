"""Tests for the LLM-as-a-judge second pass over search results."""

import json

import pytest
import src.agent.judge as judge_module
from qwen_agent.llm.schema import USER, Message
from src.agent.judge import _validate_verdicts
from src.tools.web_search import WebSearchTool
from src.websearch.protocol import SearchResponse, SearchResult
from src.websearch.provenance import get_url_provenance


def _make_tool(monkeypatch, results):
    tool = WebSearchTool()

    class FakeClient:
        def search(self, query, **kwargs):
            return SearchResponse(
                query=query,
                engines=["deepseek-official"],
                results=results,
                partial_failures=[],
            )

    tool.client = FakeClient()
    return tool


def _two_results():
    return [
        SearchResult(
            "测试规则甲 官方正文",
            "https://www.csrc.gov.cn/rule-a",
            "测试规则甲 全文 条款",
            "deepseek-official",
            "web",
        ),
        SearchResult(
            "测试规则乙 无关页面",
            "https://example.com/unrelated",
            "与测试规则甲无关的内容",
            "deepseek-official",
            "web",
        ),
    ]


def test_judge_filters_results_and_limits_provenance(monkeypatch):
    tool = _make_tool(monkeypatch, _two_results())

    def fake_judge(messages, query, candidates):
        return [candidates[0]], [
            {"title": candidates[1]["title"], "url": candidates[1]["url"], "reason": "无关"}
        ]

    monkeypatch.setattr(judge_module, "judge_search_results", fake_judge)

    payload = json.loads(
        tool.call(
            {"query": "测试规则甲 全文"},
            messages=[Message(USER, "请查一下测试规则甲的原文")],
        )
    )

    assert payload["judge"] == "applied"
    assert [item["url"] for item in payload["results"]] == [
        "https://www.csrc.gov.cn/rule-a"
    ]
    assert payload["discarded_by_judge"] == [
        {"title": "测试规则乙 无关页面", "url": "https://example.com/unrelated", "reason": "无关"}
    ]
    # Only accepted results enter source provenance.
    assert get_url_provenance("https://www.csrc.gov.cn/rule-a") is not None
    assert get_url_provenance("https://example.com/unrelated") is None


def test_judge_all_discarded_gives_rephrase_feedback(monkeypatch):
    tool = _make_tool(monkeypatch, _two_results())
    monkeypatch.setattr(
        judge_module,
        "judge_search_results",
        lambda messages, query, candidates: (
            [],
            [
                {"title": c["title"], "url": c["url"], "reason": "不相关"}
                for c in candidates
            ],
        ),
    )

    payload = json.loads(
        tool.call({"query": "测试规则甲 全文"}, messages=[Message(USER, "问")])
    )

    assert payload["judge"] == "applied"
    assert payload["results"] == []
    assert payload["quality"] == "insufficient"
    assert "discarded_by_judge" in payload["search_guidance"]
    assert len(payload["discarded_by_judge"]) == 2


def test_judge_failure_falls_back_to_heuristic_results(monkeypatch):
    tool = _make_tool(monkeypatch, _two_results())

    def broken_judge(messages, query, candidates):
        raise RuntimeError("llm down")

    monkeypatch.setattr(judge_module, "judge_search_results", broken_judge)

    payload = json.loads(
        tool.call({"query": "测试规则甲 全文"}, messages=[Message(USER, "问")])
    )

    assert payload["judge"] == "fallback:RuntimeError"
    assert len(payload["results"]) == 2
    assert payload["discarded_by_judge"] == []


def test_judge_skipped_without_active_llm_config(monkeypatch):
    tool = _make_tool(monkeypatch, _two_results())
    # conftest resets the active config; without a provider the judge cannot run
    # and the heuristic ranking must pass through unchanged.
    payload = json.loads(
        tool.call({"query": "测试规则甲 全文"}, messages=[Message(USER, "问")])
    )

    assert payload["judge"] == "fallback:JudgeUnavailable"
    assert len(payload["results"]) == 2


def test_validate_verdicts_rejects_malformed_entries():
    verdicts = _validate_verdicts(
        [
            {"index": 1, "relevant": False, "reason": "跑题"},
            {"index": "2", "relevant": True, "reason": "命中"},
            {"index": 99, "relevant": False},  # out of range
            "garbage",
        ],
        candidate_count=2,
    )
    assert verdicts == {1: (False, "跑题"), 2: (True, "命中")}

    with pytest.raises(ValueError):
        _validate_verdicts({"not": "a list"}, candidate_count=2)
    with pytest.raises(ValueError):
        _validate_verdicts([{"index": 99, "relevant": True}], candidate_count=2)


def test_relevance_effort_does_not_change_main_model_config(monkeypatch):
    from src.config.llm import get_active_llm_config, load_llm_config

    monkeypatch.setenv('DEEPSEEK_API_KEY', 'synthetic-key')
    original = load_llm_config(provider='deepseek')
    judge = judge_module.SearchResultJudge()
    assert judge.llm.generate_cfg['reasoning_effort'] == 'low'
    assert get_active_llm_config() == original
    assert 'reasoning_effort' not in original['generate_cfg']
