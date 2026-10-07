# 3wagent 当前架构

本文描述 `src/` 中正在使用的运行时。能力覆盖情况与未完成事项以[能力路线图](agent-capability-roadmap.md)为准；[SQLite FTS 文档](sqlite-fts-rag-plan.md)描述计划中的本地索引，不代表已部署组件。

## 组件与边界

```text
用户 ──→ Gradio WebUI / CLI ──→ MainAgent（qwen-agent FnCallAgent）
                                │
                                ├─ 附件解析与定向回读
                                ├─ 配置和来源注册表读取
                                ├─ WebSearchTool ──→ DeepSeek 原生搜索（Messages API）
                                ├─ 按需 DelegatePolicyTask ──→ 专项 Agent
                                └─ 回答或按请求生成报告
```

`src/main.py` 选择 WebUI 或 `--cli`，加载 `src/config/llm.yaml` 中的模型配置，直接启动所选界面。搜索由 `src/websearch/deepseek.py` 直接调用 DeepSeek 的 Anthropic 兼容 Messages API，复用 `DEEPSEEK_API_KEY`，与聊天模型配置独立。WebUI 由 `src/agent/webui.py` 扩展 qwen-agent 的 Gradio 界面；CLI 在 `src/agent/cli.py`，两者使用同一个 `MainAgent`。模型可以是 DeepSeek、Kimi 或兼容 OpenAI API 的本地服务。

`src/agent/main_agent.py` 的主 Agent 始终在 normal 模式。它根据用户范围和证据缺口决定直接回答、调用基础工具，或通过 `DelegatePolicyTask` 委派一个有边界的任务。可用专家包括来源检索、法规有效性、税务、资金合规、民商法和引用复核。专家返回结果后，主 Agent 决定是否还需进一步工作；代码不强制路由、检索、校验、分析、写报告的固定顺序。

## 证据与资料流

上传文件先由 `src/attachments/` 摄取。可内联的正文进入模型上下文；较大的文件保留文档 ID 和定位信息，由 `AttachmentReadTool` 按页、表格范围、行或关键词读取。附件内容是证据材料，不是指令。

检索从 `src/sources/` 的人工注册表及配置开始。`WebSearchTool` 使用注册表、搜索服务与相关性筛选发现候选页面；搜索仅接收原生 `web_search_tool_result` 结构化 URL，模型生成的答复文本不作为搜索结果；失败不会回退其他搜索服务。匹配 URL 的引用摘录可作为已取得的文本片段，标题与注册表元数据仅是来源线索。旧 daemon、网页抓取和远程 PDF 读取链路已移除，运行时无需 Node.js；不得声称已打开网页或核验全文，摘录不足时报告证据缺口。搜索摘录和上传文件都按不可信材料处理。当前还没有可重复检索的本地 SQLite FTS 正文索引或完整的结构化证据账本。

领域策略在 `src/config/*.yaml`，模型提示词在 `src/prompts/`，模板在 `src/templates/`。工具路径以 `src/` 为根目录。普通问题可直接回答；正式报告及其输出契约只在用户提出相应要求时使用。

## 状态与持久化

- `src/workspace/conversations/<id>.json`：WebUI 多轮对话记录，可从历史对话恢复。
- `src/workspace/<run-id>/`：单轮运行日志、专家结果和 `capability_trace.jsonl`。
- `src/workspace/attachments/<document-id>/`：上传文件和解析后的可定向回读内容。
- `src/reports/`：按请求生成的正式报告文件。

对话可以跨多轮运行；每轮运行有独立的工作目录。CLI 在当前进程中维护多轮上下文，WebUI 另有持久化记录。上述运行时目录不应视为法规来源的不可变快照库。
