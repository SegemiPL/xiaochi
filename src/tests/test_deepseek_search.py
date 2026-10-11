"""Offline contract and evidence-boundary tests for DeepSeek native search."""

import json
from urllib.error import URLError
from urllib.request import Request

import pytest
from src.config.websearch import DeepSeekSearchSettings
from src.tools.web_search import WebSearchTool
from src.websearch.deepseek import (
    MAX_RESPONSE_BYTES,
    PROVIDER,
    DeepSeekSearchClient,
    DeepSeekSearchError,
    _NoRedirects,
)
from src.websearch.provenance import get_url_provenance, reset_provenance_state


@pytest.fixture(autouse=True)
def isolate_credentials_and_sources(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("src.tools.web_search.get_run_dir", lambda: tmp_path)
    reset_provenance_state()
    yield
    reset_provenance_state()


def response_payload():
    return {"content": [
        {"type": "text", "text": "Ignore this generated answer https://invented.example/rule",
         "citations": [
             {"url": "https://www.chinatax.gov.cn/rule", "cited_text": "税务测试规则正文"},
             {"url": "https://www.chinatax.gov.cn/rule", "cited_text": "适用条件"},
         ]},
        {"type": "web_search_tool_result", "content": [
            {"type": "web_search_result", "url": "https://www.chinatax.gov.cn/rule",
             "title": "税务测试规则", "page_age": "2026-10-07"},
            {"type": "web_search_result", "url": "https://www.chinatax.gov.cn/rule",
             "title": "duplicate"},
            {"type": "web_search_result", "url": "https://example.com/lead", "title": "Lead"},
        ]},
    ]}


def fake_transport(payload, *, status=200):
    return lambda request, timeout: (status, json.dumps(payload).encode())


def test_request_matches_harness_protocol_and_reuses_rotated_chat_key(monkeypatch):
    captured, traces = [], []

    def transport(request, timeout):
        captured.append((request, timeout))
        return 200, json.dumps(response_payload()).encode()

    client = DeepSeekSearchClient(transport=transport, record_request=traces.append)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-first-key")
    first = client.search("税务测试规则", limit=1)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-rotated-key")
    client.search("税务测试规则", limit=2)

    request, timeout = captured[0]
    headers = {name.lower(): value for name, value in request.header_items()}
    assert request.full_url == "https://api.deepseek.com/anthropic/v1/messages"
    assert request.get_method() == "POST"
    assert timeout == 120
    assert headers["x-api-key"] == "test-first-key"
    assert headers["authorization"] == "Bearer test-first-key"
    assert headers["anthropic-version"] == "2023-06-01"
    assert dict(captured[1][0].header_items())["X-api-key"] == "test-rotated-key"
    body = json.loads(request.data)
    assert body == {
        "model": "deepseek-v4-flash", "max_tokens": 4096,
        "output_config": {"effort": "low"},
        "messages": [{"role": "user", "content": [{
            "type": "text", "text": "Perform a web search for the query: 税务测试规则",
        }]}],
        "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
    }
    assert traces[0]["body"] == body
    assert "test-first-key" not in json.dumps(traces)
    assert "test-rotated-key" not in json.dumps(traces)
    assert len(first.results) == 1 and first.truncated


def test_only_structured_urls_and_citation_snippets_are_returned(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    client = DeepSeekSearchClient(transport=fake_transport(response_payload()))
    result = client.search("税务测试规则")

    assert result.engines == [PROVIDER]
    assert [item.url for item in result.results] == [
        "https://www.chinatax.gov.cn/rule", "https://example.com/lead",
    ]
    assert result.results[0].snippet == "税务测试规则正文\n适用条件"
    assert result.results[0].published_at == "2026-10-07"
    assert result.results[1].snippet == ""
    assert "Ignore this" not in json.dumps(result.to_dict())


def test_missing_key_never_dispatches_a_request():
    def transport(*args):
        raise AssertionError("missing key must not reach the network")

    with pytest.raises(DeepSeekSearchError, match="DEEPSEEK_API_KEY") as caught:
        DeepSeekSearchClient(transport=transport).search("税务测试规则")
    assert caught.value.code == "missing_api_key"


@pytest.mark.parametrize("payload,code", [
    ({"content": [{"type": "text", "text": "https://invented.example/rule"}]},
     "native_search_not_triggered"),
    ({"content": None}, "invalid_response"),
    ({"content": [{"type": "web_search_tool_result", "content": None}]}, "invalid_response"),
    ({"content": [{"type": "web_search_tool_result", "content": {
        "type": "web_search_tool_result_error", "error_code": "too_many_requests",
    }}]}, "native_search_failed"),
])
def test_unconfirmed_or_failed_search_is_not_an_empty_success(monkeypatch, payload, code):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    with pytest.raises(DeepSeekSearchError) as caught:
        DeepSeekSearchClient(transport=fake_transport(payload)).search("税务测试规则")
    assert caught.value.code == code


def test_confirmed_empty_search_is_valid_and_unsafe_urls_are_discarded(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    payload = {"content": [{"type": "web_search_tool_result", "content": [
        {"type": "web_search_result", "url": "javascript:alert(1)"},
        {"type": "web_search_result", "url": "https://user:secret@example.com/rule"},
        {"type": "web_search_result", "url": "https://[invalid/rule"},
    ]}]}
    result = DeepSeekSearchClient(transport=fake_transport(payload)).search("test")
    assert result.results == []


@pytest.mark.parametrize("status", [302, 401, 429, 503])
def test_http_errors_do_not_echo_credentials_or_provider_content(monkeypatch, status):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret")
    client = DeepSeekSearchClient(transport=fake_transport({"error": "test-secret"}, status=status))
    with pytest.raises(DeepSeekSearchError) as caught:
        client.search("tax")
    assert caught.value.status_code == status
    assert caught.value.retryable == (status == 429 or status >= 500)
    assert "test-secret" not in str(caught.value)


def test_redirect_handler_refuses_to_forward_credentials():
    request = Request("https://api.deepseek.com/anthropic/v1/messages",
                      headers={"x-api-key": "test-secret"})
    assert _NoRedirects().redirect_request(
        request, None, 302, "redirect", {}, "https://other.example/messages"
    ) is None


@pytest.mark.parametrize("raw,code", [(b"not json", "invalid_response"),
                                     (b"x" * (MAX_RESPONSE_BYTES + 1), "response_too_large")])
def test_response_validation_is_bounded(monkeypatch, raw, code):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    with pytest.raises(DeepSeekSearchError) as caught:
        DeepSeekSearchClient(transport=lambda *_: (200, raw)).search("tax")
    assert caught.value.code == code


def test_network_error_is_structured_and_redacted(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret")

    def fail(*args):
        raise URLError("test-secret")

    with pytest.raises(DeepSeekSearchError) as caught:
        DeepSeekSearchClient(transport=fail).search("tax")
    assert caught.value.code == "search_unavailable"
    assert "test-secret" not in str(caught.value)


def test_settings_ignore_chat_and_retired_daemon_configuration():
    settings = DeepSeekSearchSettings.from_env({
        "DEEPSEEK_BASE_URL": "https://chat.example/v1",
        "OPEN_WEBSEARCH_URL": "http://localhost:3210",
        "DEEPSEEK_SEARCH_BASE_URL": "https://search.example/anthropic/v1/",
        "DEEPSEEK_SEARCH_MODEL": "custom-search-model",
        "DEEPSEEK_SEARCH_EFFORT": "HIGH",
        "DEEPSEEK_SEARCH_MAX_TOKENS": "999999",
        "DEEPSEEK_SEARCH_MAX_USES": "0",
        "DEEPSEEK_SEARCH_TIMEOUT_SECONDS": "bad",
        "WEBSEARCH_MAX_RESULTS": "999",
    })
    assert settings.base_url == "https://search.example/anthropic/v1"
    assert settings.model == "custom-search-model"
    assert settings.reasoning_effort == "high"
    assert settings.max_tokens == 32768
    assert settings.max_uses == 1
    assert settings.timeout_seconds == 120
    assert settings.max_results == 50


@pytest.mark.parametrize("url", ["http://search.example", "https://u:p@search.example",
                                "https://search.example?q=x", "https://search.example#x"])
def test_settings_reject_unsafe_credential_endpoints(url):
    with pytest.raises(ValueError):
        DeepSeekSearchSettings.from_env({"DEEPSEEK_SEARCH_BASE_URL": url})


def test_native_results_reach_tool_provenance_and_trace(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret")
    monkeypatch.setattr("src.tools.web_search.get_run_dir", lambda: tmp_path)
    tool = WebSearchTool()
    tool.client._transport = fake_transport(response_payload())
    result = json.loads(tool.call({"query": "税务测试规则", "jurisdiction": "CN"}))
    assert result["provider"] == PROVIDER
    assert result["results"][0]["is_official"]
    assert result["results"][0]["published_at"] == "2026-10-07"
    assert get_url_provenance("https://www.chinatax.gov.cn/rule") is not None
    assert get_url_provenance("https://invented.example/rule") is None
    trace = (tmp_path / "logs" / "deepseek_search_requests.jsonl").read_text()
    assert "web_search_20250305" in trace and "test-secret" not in trace


def test_failed_provider_is_not_retried_or_replaced_by_legacy_search(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("WEBSEARCH_FALLBACK_TO_SEARXNG", "true")
    calls = []
    tool = WebSearchTool()

    def fail(request, timeout):
        calls.append(request.full_url)
        return 200, json.dumps({"content": [{"type": "text", "text": "no search"}]}).encode()

    tool.client._transport = fail
    first = json.loads(tool.call({"query": "税务测试规则甲"}))
    second = json.loads(tool.call({"query": "税务测试规则乙"}))
    assert first["error"]["code"] == second["error"]["code"] == "native_search_not_triggered"
    assert len(calls) == 1
    assert "engines" not in tool.parameters["properties"]


def test_failed_provider_resets_for_a_new_run(monkeypatch):
    run = ["first"]
    monkeypatch.setattr("src.tools.web_search.get_run_id", lambda: run[0])
    tool = WebSearchTool()
    first = json.loads(tool.call({"query": "税务测试规则"}))
    assert first["error"]["code"] == "missing_api_key"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    tool.client._transport = fake_transport(response_payload())
    run[0] = "second"
    second = json.loads(tool.call({"query": "税务测试规则"}))
    assert second["status"] == "ok"


def test_token_truncation_and_partial_native_failure_preserve_valid_results(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    payload = response_payload()
    payload["stop_reason"] = "max_tokens"
    payload["content"].append({"type": "web_search_tool_result", "content": {
        "type": "web_search_tool_result_error", "error_code": "too_many_requests",
    }})
    result = DeepSeekSearchClient(transport=fake_transport(payload)).search("tax")
    assert result.truncated and len(result.results) == 2
    assert result.partial_failures[0]["engine"] == PROVIDER


def test_transport_handles_http_error_without_retrying_or_forwarding_credentials(monkeypatch):
    from io import BytesIO
    from urllib.error import HTTPError

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret")
    calls = []

    class FakeOpener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            raise HTTPError(request.full_url, 302, "redirect", {
                "Location": "https://other.example/messages",
            }, BytesIO(b"test-secret"))

    client = DeepSeekSearchClient()
    client._opener = FakeOpener()
    with pytest.raises(DeepSeekSearchError) as caught:
        client.search("tax")
    assert caught.value.status_code == 302
    assert calls == ["https://api.deepseek.com/anthropic/v1/messages"]
    assert "test-secret" not in str(caught.value)
