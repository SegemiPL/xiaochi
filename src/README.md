# 3wagent 运行与配置

`src/` 是当前运行时根目录，使用 [qwen-agent](https://github.com/QwenLM/qwen-agent) 管理对话与工具调用。运行所需的配置、来源注册表、模板与 Web Search 服务均位于其中。

> 当前组件和数据流见 [`docs/architecture.md`](docs/architecture.md)。
> 面向 42 道测试题的能力路线图及实时实现状态见
> [`docs/agent-capability-roadmap.md`](docs/agent-capability-roadmap.md)。

## 当前状态

主 Agent 已可在 WebUI 与 CLI 中运行，并可选择 DeepSeek、Kimi 或本地兼容 OpenAI API 的模型。附件摄取、来源搜索、正文抓取与按需专家委派已经接入；能力覆盖和端到端可靠性仍按路线图持续验证。不存在所有问题必须经过的固定子代理流水线。

## 目录结构

```
src/
├── main.py                 # WebUI / CLI 入口与搜索服务管理
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
├── infra/open-websearch/   # 固定版本的本地 Web Search daemon
├── tools/
│   ├── read_markdown_files.py  # MarkDownReadTool
│   ├── read_yaml_files.py      # YamlReadTool
│   ├── web_search.py           # WebSearchTool（候选来源发现）
│   └── web_fetch.py            # WebFetchTool（网页正文抓取）
├── websearch/
│   ├── client.py               # open-websearch daemon HTTP 客户端
│   ├── policy.py               # 法域搜索引擎和官方域名策略
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
npm ci --prefix src/infra/open-websearch
src/.venv/bin/python -m src.main                         # 默认 local 模型、WebUI
src/.venv/bin/python -m src.main --provider deepseek
src/.venv/bin/python -m src.main --provider kimi
src/.venv/bin/python -m src.main --cli --provider deepseek  # 终端交互
src/.venv/bin/python -m src.main --provider local --model <model-name>
src/.venv/bin/python -m src.main -d                       # DEBUG 模式
```

启动时会自动探测并启动本地 open-websearch daemon，随后打开 qwen-agent
内置的 Gradio WebUI（加上 `--cli` 时进入终端交互）。程序退出时会关闭本次启动的 daemon；如果 daemon
原本已经运行，则只复用、不关闭。

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

3. 首次使用时，在本地安装 OpenWebSearch 的固定版本依赖：

   ```bash
   npm ci --prefix src/infra/open-websearch
   ```

4. 确认本地能够访问转发后的 LLM API：

   ```bash
   curl http://127.0.0.1:11434/v1/models
   ```

5. 在项目根目录启动 Agent：

   ```bash
   python -m src.main
   # 或指定远程推理服务中加载的模型名
   python -m src.main -m <model-name>
   ```

程序随后会自动启动本地 OpenWebSearch、启动 Gradio WebUI，并在终端输出
WebUI 地址。浏览器中的 Agent 会自动获得 `WebSearchTool` 和
`WebFetchTool`；专业政策问题进入检索、法规有效性验证或引用核验阶段时，
Agent 会按需调用这些工具，简单对话通常不会触发搜索。

WebUI 会把每个对话的完整上下文自动保存到
`src/workspace/conversations/<conversation-id>.json`。左侧“历史对话”可以恢复此前
对话并继续追问；点击“新对话”会清空当前页面上下文，但不会删除已保存记录。

LLM 请求通过 SSH 隧道发送到远程服务器；搜索引擎访问和官方网页抓取则
从本地机器发起，因此本地网络必须能够访问所选搜索引擎及目标网站。
OpenWebSearch 启动日志位于：

```text
src/workspace/logs/open-websearch.log
```

### Web Search 配置

Web Search 使用独立的本地 `open-websearch` daemon。安装与启动方法见
[`infra/open-websearch/README.md`](infra/open-websearch/README.md)。默认地址为
`http://127.0.0.1:3210`。

可用环境变量：

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `OPEN_WEBSEARCH_URL` | `http://127.0.0.1:3210` | daemon 地址；默认只允许 localhost |
| `OPEN_WEBSEARCH_ALLOW_REMOTE` | `false` | 显式允许远程 daemon，不建议日常开启 |
| `OPEN_WEBSEARCH_AUTOSTART` | `true` | 随 `python -m src.main` 自动启动本地 daemon |
| `OPEN_WEBSEARCH_STARTUP_TIMEOUT_SECONDS` | `15` | daemon 就绪等待时间，范围 1–120 秒 |
| `OPEN_WEBSEARCH_PROXY_URL` | 空 | daemon 专用 HTTP(S) 代理；未设置 `USE_PROXY` 时优先使用 |
| `USE_PROXY` / `PROXY_URL` | 自动推断 | open-webSearch 原生代理开关；显式设置时优先级最高 |
| `WEBSEARCH_TIMEOUT_SECONDS` | `30` | 单次 HTTP 调用超时，范围 1–120 秒 |
| `WEBSEARCH_MAX_RESULTS` | `10` | 搜索结果硬上限，范围 1–50 |
| `WEBFETCH_MAX_CHARS` | `8000` | 单页正文字符硬上限，范围 1000–8000 |
| `WEBSEARCH_FALLBACK_TO_SEARXNG` | `false` | open-websearch 失败或无结果时回退旧 SearXNG |

若没有显式配置 `USE_PROXY`，启动器会把现有的 `HTTPS_PROXY`/`https_proxy` 或
`HTTP_PROXY`/`http_proxy` 转换为 open-webSearch 要求的 `USE_PROXY=true` 与
`PROXY_URL`。显式设置 `USE_PROXY=false` 可关闭自动继承。代理设置只在 daemon
启动时读取；修改环境变量后需要重启 3wagent 和仍在后台运行的旧 daemon。
若端口上已有 daemon，但其代理开关与当前进程要求不一致，3wagent 会拒绝静默
复用并给出重启提示，避免继续把不可用的海外引擎包装成正常搜索。

检索遵循：本地 `sources/` registry 优先，开放网络仅作补充；搜索摘要只能用于发现候选 URL，必须通过 `WebFetchTool` 获取官方页面正文后才能作为证据。法域对应的引擎与官方域名配置位于 `config/jurisdictions.yaml`。

`WebSearchTool` 会按查询内容自动匹配来源注册表；精确命中时直接返回已登记来源，
不消耗开放搜索请求。开放搜索结果会经过与主题无关的标题/摘要相关性评分，低相关
页面不会暴露给 Agent。若普通搜索没有相关的官方结果，但能够从注册表或候选结果
识别主管机关域名，工具会进行一次有界的官方域搜索。发生 302、验证码等引擎故障
后，该引擎会在本次运行的后续查询中自动停用，并在结果元数据中报告。

对于标记为 `CN` 且包含外汇、汇发、跨境贸易、资本项目或经常项目等关键词的
查询，`WebSearchTool` 会先调用 SAFE 官网的固定站内检索入口；只要获得结果，
便直接返回官方域名候选，不再同时调用通用搜索引擎。SAFE 的政策法规、行政规范
性文件和网上服务索引页若被通用正文抽取器误识别为页脚，`WebFetchTool` 会从
固定的 SAFE HTTPS 主机读取原始 HTML，并返回紧凑的标题、日期与具体页面链接。
该回退仅适用于三个预先允许的索引路径，不会接受模型提供的任意站点或路径。

远程 PDF 与上传 PDF 使用两条通用读取链路：`WebFetchTool` 会将来源校验通过的
公共 PDF URL 下载后用 pypdf 转换为带页码的正文；用户上传的 PDF 则由附件摄取
层解析为带 `pdf:pN` locator 的内容，未内联页面通过 `AttachmentReadTool` 读取。
这两项工具都向需要读取来源正文的 agent 开放，不依赖特定网站或 URL 路径。

`WebFetchTool` 只接受用户当前消息明确提供的 URL、本轮 `WebSearchTool` 实际
返回的 URL、`sources/` registry 中登记的 URL，或已抓取页面中的链接。模型根据标题、日期、文号或
其他页面路径自行拼接的 URL 会在联网前被拒绝；同一个返回 404 的 URL 在
本轮不会被再次请求。遇到 404 时，应按准确标题和文号搜索一次替代官方入口，
仍未找到则明确记录证据缺口，不得继续猜测路径。

每个 agent 对同一个规范化 URL 最多成功抓取一次；再次请求不会访问网络，
也不会把相同正文重复写入上下文。若模型在成功抓取、已知失败或搜索/抓取
预算耗尽后仍继续调用工具，agent 运行层会终止工具循环，并进行一次禁用工具的
最终总结。该限制是 agent 实例级的：检索与核验 agent 仍可各自独立获取同一来源。

网络超时等可重试错误对同一 URL 最多进行两次真实请求；不可重试错误只请求
一次，之后的同 URL 调用直接进入终态。参数错误不会消耗抓取预算。Python 客户端
会拒绝传统数字形式的私网 IP，并在调用 daemon 前检查 DNS 结果；bundled
`open-websearch` 还会对每次重定向及浏览器导航重复执行公网地址校验。

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
- **WebSearchTool** — 调用 open-websearch 搜索候选来源并标记官方域名
- **WebFetchTool** — 抓取候选页面正文和来源元数据；网页内容始终视为不可信证据
- **DelegatePolicyTask** — 仅在复杂问题确有必要时运行一个有界专家任务；不会启动固定流水线

## 当前自适应执行方式

`MainAgent._run()` 会先解析附件，然后让同一个 normal 模式主 agent 根据问题本身选择最小能力集合：可以直接回答，可以调用附件、配置、搜索和抓取工具，也可以通过 `DelegatePolicyTask` 单独委派来源检索、有效性核验、税务、资金合规、商事或引用复核。代码不再预设 Routing → RAG → Validate → Analyst → Citation → Report 的执行顺序。

每次工具选择写入当前 `workspace/<run-id>/capability_trace.jsonl`，用于调试实际采用的能力及原因。正式报告只在用户明确要求时使用输出契约；后续重点是扩大端到端评测样本、完善检索快照归档，并根据真实失败情况决定是否启用 Playwright 浏览器兜底。
