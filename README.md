# 3wagent

Cross-border policy research agent for Mainland China, the United States, Hong Kong, and Singapore. The current application runs from `src/` on [qwen-agent](https://github.com/QwenLM/qwen-agent). It offers a Gradio WebUI and an interactive CLI.

[简体中文](README.zh-CN.md) · [Architecture](src/docs/architecture.md) · [Runtime guide](src/README.md) · [Capability roadmap](src/docs/agent-capability-roadmap.md)

## Quick start

Run these commands from the repository root. Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node.js/npm are required. The bundled web search service needs network access to reach search engines and source sites.

```bash
uv sync --project src
npm ci --prefix src/infra/open-websearch
src/.venv/bin/python -m src.main --provider deepseek
```

Set `DEEPSEEK_API_KEY` in the environment before selecting DeepSeek. Other configured providers are `kimi` (requires `MOONSHOT_API_KEY`) and `local` (the default, an OpenAI-compatible endpoint at `127.0.0.1:11434/v1`). For a terminal session, add `--cli`:

```bash
src/.venv/bin/python -m src.main --cli --provider deepseek
```

The entry point starts or reuses the local OpenWebSearch service, then launches the selected frontend. See the [runtime guide](src/README.md) for provider, proxy, remote-model, and search configuration.

## How it works

`MainAgent`, built on qwen-agent's `FnCallAgent`, handles every request in one adaptive mode. It can answer directly, read an uploaded document, consult local configuration and source registries, search for sources, fetch original pages, or delegate a bounded task to a specialist. Delegation is optional; there is no mandatory research pipeline.

```text
WebUI / CLI
    → MainAgent
        ├─ attachment, configuration, search, fetch, and result tools
        └─ optional DelegatePolicyTask
             ├─ source research and validity review
             ├─ tax, funds compliance, and commercial-law analysis
             └─ citation review
```

The main agent decides when the available evidence is enough to answer the question. Search result summaries are leads; conclusions should be grounded in fetched official pages or located passages from uploaded documents. Formal report structure is used only when the user asks for a report.

The runtime keeps configuration, curated source registries, prompts, and report templates under `src/`. The WebUI stores conversation history in `src/workspace/conversations/`; each run stores logs, specialist results, and a capability trace under `src/workspace/<run-id>/`. Formal report files, when produced, are written under `src/reports/`.

## Current scope

- Uploaded PDF, DOCX, spreadsheet, CSV, and text files can be parsed. Large documents are read further by page, sheet, row, or query through `AttachmentReadTool`.
- `WebSearchTool` checks the curated registry and discovers candidate URLs. `WebFetchTool` retrieves HTML or PDF evidence and restricts fetching to URLs with recorded provenance.
- Optional specialists handle source research, validity, tax, funds compliance, commercial law, and citation review. The main agent remains responsible for the answer.
- DeepSeek, Kimi, and a local OpenAI-compatible model are configured in `src/config/llm.yaml`.

The [capability roadmap](src/docs/agent-capability-roadmap.md) tracks incomplete work, including structured evidence, remote-document caching, and broader evaluation. The [SQLite FTS plan](src/docs/sqlite-fts-rag-plan.md) describes a proposed local index; it is not part of the current runtime.
