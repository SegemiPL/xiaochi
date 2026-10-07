# 3wagent

Cross-border policy research agent for Mainland China, the United States, Hong Kong, and Singapore. The current application runs from `src/` on [qwen-agent](https://github.com/QwenLM/qwen-agent). It offers a Gradio WebUI and an interactive CLI.

[简体中文](README.zh-CN.md) · [Architecture](src/docs/architecture.md) · [Runtime guide](src/README.md) · [Capability roadmap](src/docs/agent-capability-roadmap.md)

## Quick start

Run these commands from the repository root. Python 3.11+ and [uv](https://docs.astral.sh/uv/) are required. Native web search uses the same `DEEPSEEK_API_KEY` as DeepSeek chat. No Node.js, search daemon, or Docker container is required.

```bash
uv sync --project src
src/.venv/bin/python -m src.main --provider deepseek
```

Set `DEEPSEEK_API_KEY` in the environment before selecting DeepSeek. Other configured providers are `kimi` (requires `MOONSHOT_API_KEY`) and `local` (the default, an OpenAI-compatible endpoint at `127.0.0.1:11434/v1`). For a terminal session, add `--cli`:

```bash
src/.venv/bin/python -m src.main --cli --provider deepseek
```

The entry point launches the selected frontend directly. Web search calls DeepSeek directly using the native Messages search protocol used by DeepSeek Harness. See the [runtime guide](src/README.md) for provider, proxy, remote-model, and search configuration.

## How it works

`MainAgent`, built on qwen-agent's `FnCallAgent`, handles every request in one adaptive mode. It can answer directly, read an uploaded document, consult local configuration and source registries, search for source URLs and excerpts, or delegate a bounded task to a specialist. Delegation is optional; there is no mandatory research pipeline.

```text
WebUI / CLI
    → MainAgent
        ├─ attachment, configuration, search, and result tools
        └─ optional DelegatePolicyTask
             ├─ source research and validity review
             ├─ tax, funds compliance, and commercial-law analysis
             └─ citation review
```

The main agent decides when the available evidence is enough to answer the question. Search result summaries are leads; conclusions should be grounded in returned official citation excerpts or located passages from uploaded documents. Full-page retrieval is not available, and missing source text must be reported. Formal report structure is used only when the user asks for a report.

The runtime keeps configuration, curated source registries, prompts, and report templates under `src/`. The WebUI stores conversation history in `src/workspace/conversations/`; each run stores logs, specialist results, and a capability trace under `src/workspace/<run-id>/`. Formal report files, when produced, are written under `src/reports/`.

## Current scope

- Uploaded PDF, DOCX, spreadsheet, CSV, and text files can be parsed. Large documents are read further by page, sheet, row, or query through `AttachmentReadTool`.
- `WebSearchTool` uses the curated registry for authority hints and discovers candidate URLs through DeepSeek native search (`web_search_20250305`). It requires `DEEPSEEK_API_KEY` for network search even when chat uses Kimi or a local model, and never falls back to DuckDuckGo/Bing/SearXNG. Only structured search results and citation excerpts are retained; the old search/fetch daemon and tools have been removed.
- Optional specialists handle source research, validity, tax, funds compliance, commercial law, and citation review. The main agent remains responsible for the answer.
- DeepSeek, Kimi, and a local OpenAI-compatible model are configured in `src/config/llm.yaml`.

The [capability roadmap](src/docs/agent-capability-roadmap.md) tracks incomplete work, including structured evidence, remote-document caching, and broader evaluation. The [SQLite FTS plan](src/docs/sqlite-fts-rag-plan.md) describes a proposed local index; it is not part of the current runtime.
