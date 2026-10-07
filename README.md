# Xiaochi Agent

Xiaochi is a government tax-work assistant built on the 3wagent core. It helps staff query tax policies, read uploaded materials, draft consultation replies and check calculations. Mainland China is the default jurisdiction; foreign jurisdictions are considered when requested.

[简体中文](README.zh-CN.md) · [Runtime guide](src/README.md) · [Architecture](src/docs/architecture.md) · [Capability roadmap](src/docs/agent-capability-roadmap.md)

## Features

- Independent chat interface with conversation history, new chats, uploads, policy links and answer copying.
- PDF, DOCX, spreadsheet, CSV and text parsing, with up to five attachments per question and 25 MB per file.
- Direct conclusions with relevant conditions and policy evidence. Initial clarification asks for at most three key facts. Reports and reply drafts are generated when requested.
- Final answers only in Web and CLI. Reasoning, tool calls, tool responses and specialist messages stay on the backend; history restoration uses a separate public transcript.
- While waiting, the Web interface shows actual execution stages and elapsed seconds, without exposing reasoning or tool arguments. The Chinese agent name is 小弛.

Every final answer receives this programmatically appended disclaimer:

> 以上内容由 AI 生成，仅供参考，具体请以现行有效政策及主管税务机关确认口径为准。

## Quick start

Use Python 3.11+ and [uv](https://docs.astral.sh/uv/). Run all commands from the repository root.

### 1. Configure the key

Create `.env` at the repository root with your own DeepSeek key:

```dotenv
DEEPSEEK_API_KEY=your-deepseek-api-key
```

Git ignores `.env` and `.env.*`. The application loads the file from a fixed repository path; exporting it manually is unnecessary. Existing process variables take precedence. Restart after editing `.env`. Keep real credentials out of README and YAML files.

### 2. Install and start

```bash
uv sync --project src
src/.venv/bin/python -m src.main
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). DeepSeek is the default chat provider. Chat and native web search share the key in `.env`. Node.js, Docker and a search daemon are unnecessary.

### 3. Other startup options

```bash
src/.venv/bin/python -m src.main --cli                 # Terminal interface
src/.venv/bin/python -m src.main --port 8002           # Different Web port
src/.venv/bin/python -m src.main --provider kimi       # Requires MOONSHOT_API_KEY
src/.venv/bin/python -m src.main --provider local      # Local OpenAI-compatible model
```

Search still uses DeepSeek and requires `DEEPSEEK_API_KEY` when chat uses another provider. See the [runtime guide](src/README.md) for model, proxy and search settings.

## Architecture and configuration

```text
Independent HTML/CSS/JavaScript frontend
    → FastAPI → ChatService → MainAgent (qwen-agent)
        ├─ Attachment parsing and targeted reading
        ├─ Configuration and official-source registries
        ├─ DeepSeek native web search
        └─ Optional specialist tasks
    → Final-answer extraction and AI-reference disclaimer
```

The former Gradio frontend and legacy search daemon have been removed. Internal conversation context, attachments and optional specialist capabilities continue to use the Agent core. There is no mandatory research pipeline.

Ordinary consultation targets about 300 Chinese characters. Operation questions with missing key facts receive clarification before targeted research. Search and DeepSeek relevance review use lower reasoning effort while the main answer retains its configured reasoning settings. New answers and restored history share Markdown rendering with support for bold text adjacent to Chinese punctuation.

| Configuration | Purpose |
|---|---|
| [src/config/xiaochi.yaml](src/config/xiaochi.yaml) | Identity, default jurisdiction, scenarios, answer style, suggested questions and disclaimer |
| [src/config/llm.yaml](src/config/llm.yaml) | DeepSeek, Kimi and local chat providers |
| [src/config/jurisdictions.yaml](src/config/jurisdictions.yaml) | Jurisdictions and official-domain policy |
| [src/config/output-contract.yaml](src/config/output-contract.yaml) | Tax-work report structure, applied when requested |
| [src/templates/report.md](src/templates/report.md) | Report and reply-draft template |

## Search and evidence boundaries

Search uses DeepSeek Harness's `web-search-deepseek` Messages protocol with native `web_search_20250305`. Only structured sources and URL-associated citation excerpts are accepted. Generated summaries are not scraped for links, and search never falls back to DuckDuckGo, Bing or SearXNG.

`WebSearchTool` reads relevant official HTML articles after discovery and returns source text, final URL, read time, content hash and truncation status. It reads up to three pages concurrently, tries other official candidates after failures, and caches successful reads in memory for 15 minutes. Titles, URLs and generated summaries alone do not establish policy provisions.

The main Agent retains autonomous tool selection and optional specialist delegation. The three-request shared limit and forced finalization on URL-only results have been removed. It stops once evidence suffices for the scoped question; progress messages report actual execution stages. Existing per-agent search protection and duplicate-query checks remain.

**Live check on 2026-10-07:** The dividend-policy question retrieved official text and correctly identified Announcement 2026 No. 27, its September 1 execution date, the covered individuals and enterprises, the 20% rate and repeal of the previous provision. This verifies one case, not general tax-policy accuracy.

Remote PDFs, JavaScript-dependent pages and a local policy-text index remain unsupported. Uploaded PDFs support page-level reading. Unreadable sources and matters unspecified by the text are reported as specific evidence gaps.

## Testing and iteration

Install development dependencies and run offline regression tests:

```bash
uv sync --project src --extra dev
src/.venv/bin/python -m pytest -q src/tests
```

Run the opt-in live DeepSeek behavior evaluation:

```bash
src/.venv/bin/python -m src.evals.xiaochi_smoke
```

This command consumes API usage and uses isolated temporary conversations. It writes a report to `src/workspace/eval/xiaochi-smoke.json` without keys, headers or full model configuration.

| Validation | Result on 2026-10-07 |
|---|---|
| Offline regression | 199 tests passed |
| Live model checks | 8/8 passed: identity, supplied-input calculation, follow-up rewriting, tax-input clarification, cross-border operation clarification, attachments, official-link discovery and document/date/scope verification for a recent-policy question |
| Browser checks | Desktop and mobile layout, waiting indicator, final answers and history restoration checked; real calculation and Chinese bold rendering verified |

Latest checks: initial clarification took 2.13 seconds, official-link discovery 11.16 seconds, and the complete dividend-policy answer 55.24 seconds with four search-tool calls. The previous 16.22-second evidence-gap reply did not answer the question and is not a successful speed benchmark. The regression checks retrieved official clauses and the final document name, number, execution date, rate, scope and repeal.

These eight cases establish product behavior and one policy regression. The full 42-question evaluation and broader policy accuracy remain unaccepted. See the [capability roadmap](src/docs/agent-capability-roadmap.md).

## Runtime scope and data

History entries support confirmed deletion and undo. Desktop controls appear on hover or keyboard focus; touch devices show them directly. Deleting the current conversation opens a new chat, while deleting another preserves the current answer and draft. History mutations are blocked during agent execution. Removed records stay in the conversation directory's `.trash/`; uploads and run logs are retained. This is recoverable history removal, not a data purge.

This is a local single-user version, bound to `127.0.0.1` by default, without accounts or departmental permissions. Some core state remains process-global, so execution is serialized within one process. Multiple workers are not supported.

Conversations, uploads, parsed documents and logs live in Git-ignored `src/workspace/`; requested report files live in `src/reports/`. Private context and public history are persisted separately. HTTP responses expose only public messages, and static routes do not expose workspace or model configuration.
