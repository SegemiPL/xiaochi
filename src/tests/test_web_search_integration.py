"""Search integration, source provenance, and agent tool-contract tests."""

import json
from pathlib import Path

import pytest
from src.websearch.policy import is_official_url, load_jurisdiction_search_policy
from src.websearch.protocol import SearchResponse, SearchResult
from src.websearch.provenance import (
    get_url_provenance,
    register_user_provided_urls,
    reset_provenance_state,
)


@pytest.fixture(autouse=True)
def _reset_web_provenance():
    reset_provenance_state()
    yield
    reset_provenance_state()


def test_src_is_the_self_contained_runtime_root():
    from src.tools.common import PROJECT_ROOT, resolve_project_path

    expected_root = Path(__file__).resolve().parents[1]
    assert PROJECT_ROOT == expected_root
    for relative_path in (
        "config/jurisdictions.yaml",
        "config/routing.yaml",
        "config/source-levels.yaml",
        "config/output-contract.yaml",
        "sources/cn.yaml",
        "templates/report.md",
        "websearch/deepseek.py",
    ):
        assert resolve_project_path(relative_path).is_file()

    with pytest.raises(ValueError):
        resolve_project_path("../config/jurisdictions.yaml")


def test_jurisdiction_policy_and_official_domain_matching():
    policy = load_jurisdiction_search_policy("CN")

    assert policy is not None
    assert policy.engines == ["deepseek-official"]
    assert is_official_url("https://sub.safe.gov.cn/policy", policy.official_domains)
    assert is_official_url("https://szs.mof.gov.cn/policy", policy.official_domains)
    assert not is_official_url("https://safe.gov.cn.example.com/fake", policy.official_domains)


def test_every_jurisdiction_has_web_search_policy():
    for jurisdiction in ("CN", "US", "HK", "SG"):
        policy = load_jurisdiction_search_policy(jurisdiction)
        assert policy is not None
        assert policy.engines
        assert policy.official_domains


def test_qwen_search_tool_marks_and_prioritizes_official_results(monkeypatch):
    from src.tools.web_search import WebSearchTool

    tool = WebSearchTool()

    class FakeClient:
        def search(self, query, **kwargs):
            return SearchResponse(
                query=query,
                engines=["deepseek-official"],
                results=[
                    SearchResult("Commentary", "https://example.com/post", "", "deepseek-official", "web"),
                    SearchResult(
                        "Quarterly widget filing",
                        "https://www.irs.gov/payments",
                        "",
                        "deepseek-official",
                        "web",
                    ),
                ],
            )

    tool.client = FakeClient()
    payload = json.loads(tool.call({"query": "quarterly widget filing", "jurisdiction": "US"}))

    assert payload["status"] == "ok"
    assert payload["results"][0]["title"] == "Quarterly widget filing"
    assert payload["quality"] == "leads_only"
    assert payload["official_excerpt_results"] == 0
    assert "NO source text" in payload["search_guidance"]
    assert payload["results"][0]["is_official"] is True
    assert "untrusted" in payload["untrusted_content_notice"].lower()


def test_main_agent_exposes_direct_tools_and_optional_specialists(monkeypatch):
    from qwen_agent.agents import FnCallAgent
    from src.agent.main_agent import MainAgent

    def fake_agent_init(self, function_list=None, **kwargs):
        self.assigned_tools = list(function_list or [])

    monkeypatch.setattr(FnCallAgent, "__init__", fake_agent_init)
    agent = MainAgent(llm=None)

    expected_web_tools = {"WebSearchTool"}
    # Normal mode remains agentic: the main model can retrieve directly and
    # may choose one bounded specialist without entering a fixed workflow.
    assert expected_web_tools.issubset(agent.assigned_tools)
    assert not {"WebFetchTool", "SearxngSearchTool"}.intersection(agent.assigned_tools)
    assert agent.delegate_tool in agent.assigned_tools
    assert set(agent.delegate_tool.capabilities) == {
        "source_research",
        "validity_review",
        "tax_analysis",
        "funds_analysis",
        "commercial_analysis",
        "citation_review",
    }
    for name in ("source_research", "validity_review", "citation_review"):
        assert expected_web_tools.issubset(
            agent.specialists[name].assigned_tools
        )
    for name in ("tax_analysis", "funds_analysis", "commercial_analysis"):
        assert expected_web_tools.isdisjoint(
            agent.specialists[name].assigned_tools
        )
    for specialist in agent.specialists.values():
        assert not {"WebFetchTool", "SearxngSearchTool"}.intersection(specialist.assigned_tools)
    assert not hasattr(agent, "mode_detector")
    assert not hasattr(agent, "routing_agent")


def test_main_prompt_allows_source_research_without_scope_expansion():
    from src.prompts.prompts import MAIN_AGENT_SYS_PROMPT

    assert "available tools autonomously in normal mode" in MAIN_AGENT_SYS_PROMPT
    assert "search for the official source" in MAIN_AGENT_SYS_PROMPT
    assert "Do not add definitions of adjacent terms" in MAIN_AGENT_SYS_PROMPT
    assert "There is no mandatory research sequence" in MAIN_AGENT_SYS_PROMPT
    assert "Stop researching once" in MAIN_AGENT_SYS_PROMPT
    assert "deterministic calculation with complete inputs" in MAIN_AGENT_SYS_PROMPT


def test_user_message_urls_are_registered_as_source_provenance():
    url = "https://example.com/policy.pdf"

    extracted = register_user_provided_urls(f"请读取[{url}]({url})&#x20;")

    assert extracted == [url]
    assert get_url_provenance(url) == "user_provided_url"


def test_qwen_search_tool_enforces_run_budget(monkeypatch):
    from src.tools import web_search as web_search_module
    from src.tools.web_search import WebSearchTool

    monkeypatch.setattr(web_search_module, "SEARCH_BUDGET_PER_AGENT", 2)
    # The budget is per tool instance (each agent holds its own), so a fresh
    # instance always starts with a clean counter.
    tool = WebSearchTool()

    class FakeClient:
        def search(self, query, **kwargs):
            return SearchResponse(
                query=query,
                engines=["deepseek-official"],
                results=[SearchResult(query, "https://www.irs.gov/payments", query, "deepseek-official", "web")],
            )

    tool.client = FakeClient()
    assert json.loads(tool.call({"query": "alpha", "jurisdiction": "US"}))["status"] == "ok"
    assert json.loads(tool.call({"query": "bravo", "jurisdiction": "US"}))["status"] == "ok"

    payload = json.loads(tool.call({"query": "charlie", "jurisdiction": "US"}))
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "search_budget_exhausted"
    assert "STOP searching" in payload["error"]["message"]


def test_terminal_search_result_stops_the_agent_tool_loop():
    from src.agent.tool_loop_guard import (
        TerminalToolResult,
        raise_for_terminal_tool_result,
    )

    result = json.dumps(
        {
            "status": "error",
            "error": {"code": "search_budget_exhausted", "message": "use existing content"},
        }
    )

    with pytest.raises(TerminalToolResult) as caught:
        raise_for_terminal_tool_result("WebSearchTool", result)

    assert caught.value.code == "search_budget_exhausted"
    assert caught.value.tool_name == "WebSearchTool"


def test_official_links_without_text_do_not_force_premature_finalization():
    from src.agent.tool_loop_guard import raise_for_terminal_tool_result

    payload = {'status': 'ok', 'quality': 'leads_only', 'official_results': 1,
               'results': [{'url': 'https://www.chinatax.gov.cn/example', 'snippet': ''}]}
    raise_for_terminal_tool_result('WebSearchTool', json.dumps(payload))


def test_main_agent_terminal_tool_result_forces_tool_free_finalization(monkeypatch):
    from qwen_agent.agents import FnCallAgent
    from qwen_agent.llm.schema import ASSISTANT, USER, FunctionCall, Message
    from src.agent.main_agent import MainAgent
    from src.agent.tool_loop_guard import TerminalToolResult

    reasoning_only = Message(
        role=ASSISTANT,
        content="",
        reasoning_content="I should repeat the web search.",
    )
    repeated_call = Message(
        role=ASSISTANT,
        content="",
        function_call=FunctionCall(
            name="WebSearchTool",
            arguments='{"query": "policy"}',
        ),
    )

    def fake_fncall_run(self, messages, **kwargs):
        yield [reasoning_only, repeated_call]
        raise TerminalToolResult(
            tool_name="WebSearchTool",
            result=json.dumps(
                {
                    "status": "error",
                    "error": {"code": "search_budget_exhausted", "message": "use cached evidence"},
                }
            ),
            code="search_budget_exhausted",
        )

    finalization_calls = []

    def fake_call_llm(self, messages, functions=None, **kwargs):
        finalization_calls.append({"messages": messages, "functions": functions})
        yield [Message(role=ASSISTANT, content="final answer from existing evidence")]

    monkeypatch.setattr(FnCallAgent, "_run", fake_fncall_run)
    monkeypatch.setattr(MainAgent, "_call_llm", fake_call_llm)
    agent = object.__new__(MainAgent)

    frames = list(agent._run_fncall_with_guard([Message(role=USER, content="question")]))

    assert len(finalization_calls) == 1
    assert finalization_calls[0]["functions"] == []
    assert "search_budget_exhausted" in finalization_calls[0]["messages"][-1]["content"]
    assert all(
        message.content or message.role != ASSISTANT
        for message in finalization_calls[0]["messages"]
    )
    assert all(
        not message.function_call
        for message in finalization_calls[0]["messages"]
    )
    assert frames[-1][-1]["content"] == "final answer from existing evidence"


def test_user_message_url_with_parentheses_is_registered_intact():
    url = "https://en.wikipedia.org/wiki/Value-added_tax_(China)"

    extracted = register_user_provided_urls(f"请读取 {url} 这个页面")

    assert extracted == [url]
    assert get_url_provenance(url) == "user_provided_url"


def test_markdown_link_closing_paren_is_stripped_but_balanced_parens_kept():
    url = "https://example.com/wiki/Foo_(bar)"

    extracted = register_user_provided_urls(f"见 [{url}]({url})")

    assert extracted == [url]
    assert get_url_provenance(url) == "user_provided_url"


@pytest.mark.parametrize("use_cli", [False, True])
def test_entrypoint_launches_selected_frontend_without_local_service(monkeypatch, use_cli):
    from types import SimpleNamespace

    from src import main as main_module
    from src.agent import cli as cli_module

    calls = []
    monkeypatch.setattr(main_module, "parse_args", lambda: SimpleNamespace(
        DEBUG=False, cli=use_cli, model="test-model", provider="deepseek", llm_config=None,
        host="127.0.0.1", port=8000,
    ))
    monkeypatch.setattr(main_module, "run_3wagent", lambda **kwargs: calls.append(("webui", kwargs)))
    monkeypatch.setattr(cli_module, "run_cli_3wagent", lambda **kwargs: calls.append(("cli", kwargs)))
    main_module.main()
    assert calls == [("cli" if use_cli else "webui", {
        "model_name": "test-model", "provider": "deepseek", "config_path": None,
        **({} if use_cli else {"host": "127.0.0.1", "port": 8000}),
    })]
