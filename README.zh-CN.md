# 3wagent

3wagent 是面向中国内地、美国、香港和新加坡的跨境政策研究 Agent。当前应用以 `src/` 中的 [qwen-agent](https://github.com/QwenLM/qwen-agent) 运行时为核心，提供 Gradio WebUI 和交互式 CLI。

[English](README.md) · [架构说明](src/docs/architecture.md) · [运行与配置](src/README.md) · [能力路线图](src/docs/agent-capability-roadmap.md)

## 快速开始

在仓库根目录执行。需要 Python 3.11+、[uv](https://docs.astral.sh/uv/)；联网搜索复用 `DEEPSEEK_API_KEY`，无需 Node.js、搜索 daemon 或 Docker。

```bash
uv sync --project src
src/.venv/bin/python -m src.main --provider deepseek
```

选择 DeepSeek 前，先在环境变量中设置 `DEEPSEEK_API_KEY`。另有 `kimi`（需要 `MOONSHOT_API_KEY`）和默认的 `local` 配置；后者连接 `127.0.0.1:11434/v1` 上兼容 OpenAI API 的模型服务。终端交互模式加上 `--cli`：

```bash
src/.venv/bin/python -m src.main --cli --provider deepseek
```

入口程序直接启动所选界面。联网搜索改为直接调用 DeepSeek Harness 所用的原生 Messages 搜索接口。模型、代理、远程模型与搜索配置见[运行指南](src/README.md)。

## 当前架构

主 Agent `MainAgent` 基于 qwen-agent 的 `FnCallAgent`。所有请求都进入同一个自适应模式：它可以直接回答、读取上传附件、查询本地配置与来源注册表、搜索来源 URL 与引用摘录，也可以按需将一个明确的专项任务交给专家 Agent。专家委派不是固定流水线的必经步骤。

```text
WebUI / CLI
    → MainAgent
        ├─ 附件、配置、搜索与结果工具
        └─ 按需调用 DelegatePolicyTask
             ├─ 来源检索、法规有效性核验
             ├─ 税务、资金合规、民商法分析
             └─ 引用复核
```

主 Agent 判断证据何时足以回答当前问题。搜索摘要只用于发现候选来源；结论应依据返回的官方引用摘录或上传材料中可定位的段落。当前不提供网页全文抓取；原文不足时必须说明证据缺口。只有用户要求正式报告时，才使用报告结构。

运行所需的配置、来源注册表、提示词和报告模板都位于 `src/`。WebUI 对话记录保存在 `src/workspace/conversations/`；每轮运行的日志、专家结果和能力选择轨迹保存在 `src/workspace/<run-id>/`。需要正式报告时，文件写入 `src/reports/`。

## 已有能力与边界

- 支持解析上传的 PDF、DOCX、电子表格、CSV 和文本文件；大文件可通过 `AttachmentReadTool` 按页、工作表、行或查询定向读取。
- `WebSearchTool` 利用来源注册表推断权威域名，通过 DeepSeek 原生搜索（`web_search_20250305`）发现候选 URL；即使聊天使用 Kimi 或本地模型，联网搜索也需要 `DEEPSEEK_API_KEY`，失败不会回退 DuckDuckGo/Bing/SearXNG。仅保留结构化搜索结果与引用摘录；旧搜索／抓取 daemon 及工具已移除。
- 可选专家负责来源检索、有效性、税务、资金合规、民商法与引用复核；最终回答由主 Agent 负责。
- `src/config/llm.yaml` 配置 DeepSeek、Kimi 和兼容 OpenAI API 的本地模型。

[能力路线图](src/docs/agent-capability-roadmap.md)记录尚未完成的结构化证据、远程文档缓存和评测等工作。[SQLite FTS 计划](src/docs/sqlite-fts-rag-plan.md)是拟议的本地索引方案，当前运行时尚未实现。
