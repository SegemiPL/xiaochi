# 3wagent 运行与配置

`src/` 是当前运行时根目录，使用 [qwen-agent](https://github.com/QwenLM/qwen-agent) 管理对话与工具调用。运行所需的配置、来源注册表、模板与 DeepSeek 搜索客户端均位于其中。

> 当前组件和数据流见 [`docs/architecture.md`](docs/architecture.md)。
> 面向 42 道测试题的能力路线图及实时实现状态见
> [`docs/agent-capability-roadmap.md`](docs/agent-capability-roadmap.md)。

## 当前状态

主 Agent 已可在 WebUI 与 CLI 中运行，并可选择 DeepSeek、Kimi 或本地兼容 OpenAI API 的模型。附件摄取、DeepSeek 来源搜索与按需专家委派已经接入；能力覆盖和端到端可靠性仍按路线图持续验证。不存在所有问题必须经过的固定子代理流水线。

## 目录结构

```
src/
├── main.py                 # WebUI / CLI 入口
├── pyproject.toml          # 独立包 3wagent-refactor，依赖 qwen-agent[gui,python-executor]
├── environment.yml         # 等价的 conda 环境定义（python 3.12）
├── agent/
│   ├── attachments.py      # 将上传的文本附件安全地内联到模型上下文
│   ├── main_agent.py       # 自适应 MainAgent(FnCallAgent)
│   ├── cli.py              # 终端交互界面
│   ├── webui.py            # Gradio 界面与历史对话
│   └── subagent.py         # 按需调用的专项 Agent
├── config/
│   ├── llm.py              # LLM provider 配置加载器
│   ├── llm.yaml            # DeepSeek / Kimi / local provider 配置
│   ├── webui.py            # Gradio WebUI 的 chatbot 配置（prompt 建议）
│   ├── logger.py           # 单轮日志写入 src/workspace/<run-id>/logs/<model>.log
│   └── *.yaml              # 路由、法域、来源等级与输出契约
├── sources/                # 各法域官方来源注册表
├── templates/              # 报告与检索任务模板
├── tools/
│   ├── read_markdown_files.py  # MarkDownReadTool
│   ├── read_yaml_files.py      # YamlReadTool
│   └── web_search.py           # WebSearchTool（候选来源发现）
├── websearch/
│   ├── deepseek.py             # DeepSeek 原生 Messages 搜索客户端
│   ├── policy.py               # 法域搜索提供方和官方域名策略
│   └── protocol.py             # 稳定的内部返回结构
├── prompts/
│   └── prompts.py          # MAIN_AGENT_SYS_PROMPT 系统提示词
├── reports/                # 按请求生成的正式报告（Git 忽略）
└── workspace/              # 对话、单轮运行产物与日志（Git 忽略）
```

## 运行方式

```bash
# 在项目根目录（src/ 的上一级）执行
uv sync --project src
src/.venv/bin/python -m src.main                         # 默认 local 模型、WebUI
src/.venv/bin/python -m src.main --provider deepseek
src/.venv/bin/python -m src.main --provider kimi
src/.venv/bin/python -m src.main --cli --provider deepseek  # 终端交互
src/.venv/bin/python -m src.main --provider local --model <model-name>
src/.venv/bin/python -m src.main -d                       # DEBUG 模式
```

启动时直接打开 Gradio WebUI（加上 `--cli` 时进入终端交互）。
无需 Node.js、npm、搜索 daemon 或 Docker；联网搜索从 Python 直接调用 DeepSeek。

### 外部模型 API + 本地 Agent

`src/config/llm.yaml` 是 LLM provider 的配置入口，当前内置 `deepseek`、
`kimi` 和原有的 `local` 三个配置。DeepSeek 与 Kimi 都使用 OpenAI-compatible
Chat Completions 接口；API key 只从环境变量读取，不应写进 YAML 或提交到 Git。

先设置对应密钥：

```bash
export DEEPSEEK_API_KEY="你的 DeepSeek API key"
# 或：export MOONSHOT_API_KEY="你的 Kimi API key"
```

然后启动：

```bash
python -m src.main --provider deepseek
python -m src.main --provider kimi
python -m src.main --llm-config path/to/my-llm.yaml --provider my-provider
```

如需换模型，可以用 `--model` 覆盖 YAML 中的模型名；如需新增 provider，复制
`llm.yaml` 中的一个 provider，修改 `model`、`model_server` 和 `api_key_env` 即可。
如果不想修改仓库内的默认文件，可用 `--llm-config path/to/my-llm.yaml` 指向自己的配置。

### 远程部署模型 + 本地 Agent（兼容保留）

LLM 推理服务可以运行在远程 GPU 服务器，Agent、Gradio WebUI 和 Web
Search 运行在本地。推荐启动顺序如下。

1. 在远程服务器启动 OpenAI API 兼容的 LLM 推理服务。
2. 通过 SSH 将远程推理端口转发到本地 `127.0.0.1:11434`。例如远程服务
   监听 `8000` 时：

   ```bash
   ssh -N -L 11434:127.0.0.1:8000 <user>@<server>
   ```

3. 确认本地能够访问转发后的 LLM API：

   ```bash
   curl http://127.0.0.1:11434/v1/models
   ```

4. 在项目根目录启动 Agent：

   ```bash
   python -m src.main
   # 或指定远程推理服务中加载的模型名
   python -m src.main -m <model-name>
   ```

程序直接启动 Gradio WebUI 并输出地址。浏览器中的 Agent 使用 `WebSearchTool`
按需搜索；简单对话通常不会触发联网。

WebUI 会把每个对话的完整上下文自动保存到
`src/workspace/conversations/<conversation-id>.json`。左侧“历史对话”可以恢复此前
对话并继续追问；点击“新对话”会清空当前页面上下文，但不会删除已保存记录。

本地模型的 LLM 请求通过 SSH 隧道发送到远程服务器；联网搜索从本机调用 DeepSeek API，
需要另外设置 `DEEPSEEK_API_KEY`。

### Web Search 配置

`WebSearchTool` 直接采用 DeepSeek Harness 的 `web-search-deepseek` 协议：
向 `https://api.deepseek.com/anthropic/v1/messages` 发起独立的 Messages 请求，
声明原生服务端工具 `web_search_20250305`。默认模型、输出上限和搜索次数与
[官方 Harness](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/web/web-search-deepseek)
一致。每次搜索消耗一个模型轮次，最多触发 5 次服务端搜索。

搜索与 DeepSeek 聊天共用 `DEEPSEEK_API_KEY`，每次请求从环境重新读取，因此密钥轮换
不需要重建客户端。聊天选择 Kimi 或本地模型时，联网搜索仍使用 DeepSeek。
搜索端点独立于聊天端点，不继承 `DEEPSEEK_BASE_URL`。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 必需 | 与 DeepSeek 聊天使用同一密钥 |
| `DEEPSEEK_SEARCH_BASE_URL` | `https://api.deepseek.com/anthropic/v1` | HTTPS 搜索基址，自动追加 `/messages` |
| `DEEPSEEK_SEARCH_MODEL` | `deepseek-v4-flash` | 独立搜索模型，与 Harness 默认值一致，可显式覆盖 |
| `DEEPSEEK_SEARCH_MAX_TOKENS` | `4096` | 单次输出 token 上限，范围 1–32768 |
| `DEEPSEEK_SEARCH_MAX_USES` | `5` | 单次服务端搜索次数上限，范围 1–5 |
| `DEEPSEEK_SEARCH_TIMEOUT_SECONDS` | `120` | 搜索 HTTP 超时，范围 1–600 秒 |
| `WEBSEARCH_MAX_RESULTS` | `10` | 提供给 agent 的候选结果上限，范围 1–50 |

只接受 `web_search_tool_result` 中的结构化结果；标题、URL、`page_age` 保留为
来源元数据，匹配 URL 的 `cited_text` 拼接为摘要。重复 URL 去重，超量结果会被截断并标记；
模型生成的答复正文不会作为搜索结果，也不会从中提取 URL。没有结构化搜索块、原生工具错误、
HTTP 错误或缺少密钥都返回明确错误；不会自动切换到 DuckDuckGo、Bing 或 SearXNG。
同一工具在本轮发生提供方故障后暂停后续联网搜索，下轮重新尝试，本地注册表与附件仍可读取。
密钥不会写入返回结果或 `workspace/<run-id>/logs/deepseek_search_requests.jsonl` 请求轨迹。

检索仍遵循：来源注册表辅助、准确标题查询、相关性审查与官方域优先。必要时进行一次有界
`site:` 查询重试，结果仍通过 DeepSeek 获取。标题与注册表元数据仅用于发现候选 URL；引用摘录可用于支持其覆盖范围内的结论。
当前没有网页或远程 PDF 全文抓取工具，原文缺失或摘录不足时必须说明证据缺口。官方域名配置位于 `config/jurisdictions.yaml`，
各法域的搜索提供方统一为 `deepseek-official`，模型不再选择搜索引擎。

DeepSeek HTTP 客户端遵循标准 HTTP(S) 代理环境变量。旧 OpenWebSearch daemon、
SearXNG 工具、SAFE 站内搜索及 WebFetchTool 已删除，不再读取旧 daemon／抓取配置。
上传 PDF 仍由附件摄取层解析，支持通过 `AttachmentReadTool` 按 `pdf:pN` 回读。

### LLM 配置

LLM 配置位于 `src/config/llm.yaml`，由 `src/config/llm.py` 加载。provider 的结构为：

- `model`: 服务商要求的模型 ID
- `model_server`: OpenAI-compatible base URL
- `api_key_env`: 存放密钥的环境变量名
- `generate_cfg`: qwen-agent 的生成参数

不同服务商对生成参数的约束可能不同；例如内置 Kimi K2.5 配置默认不额外传递
`temperature` 和 `top_p`。

也可以设置 `LLM_PROVIDER=kimi`，作为 `--provider` 之外的环境变量方式。

## 架构要点

| 维度 | 说明 |
|---|---|
| Agent 基类 | `FnCallAgent`（function-call 风格，非 Assistant/ReActChat） |
| 前端 | qwen-agent 内置 `qwen_agent.gui.WebUI`（Gradio） |
| 工具注册 | `@register_tool` + `BaseTool`，在 `main_agent.py` 中 import 触发注册，以字符串名传给 `function_list`（未使用 MCP） |
| 系统提示词 | `MAIN_AGENT_SYS_PROMPT`，定义 normal 模式下的自适应回答、证据边界与按需专家委派规则 |
| 领域策略 | `src/config/*.yaml`（工具中的运行时相对路径为 `config/*.yaml`），由提示词引导模型用 `YamlReadTool` 自行读取 |

主要工具：

- **MarkDownReadTool** — 读取 Markdown 文件全文（入参 `file_path`）
- **YamlReadTool** — 读取 YAML 文件全文（入参 `file_path`）
- **WebSearchTool** — 调用 DeepSeek 原生搜索发现候选来源并标记官方域名
- **DelegatePolicyTask** — 仅在复杂问题确有必要时运行一个有界专家任务；不会启动固定流水线

## 当前自适应执行方式

`MainAgent._run()` 会先解析附件，然后让同一个 normal 模式主 agent 根据问题本身选择最小能力集合：可以直接回答，可以调用附件、配置和 DeepSeek 搜索工具，也可以通过 `DelegatePolicyTask` 单独委派来源检索、有效性核验、税务、资金合规、商事或引用复核。代码不再预设 Routing → RAG → Validate → Analyst → Citation → Report 的执行顺序。

每次工具选择写入当前 `workspace/<run-id>/capability_trace.jsonl`，用于调试实际采用的能力及原因。正式报告只在用户明确要求时使用输出契约；后续重点是扩大端到端评测样本、完善检索快照归档，并根据真实失败情况决定是否启用 Playwright 浏览器兜底。
