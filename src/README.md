# 小弛运行与配置

`src/` 是当前运行时根目录，使用 qwen-agent 的 `FnCallAgent` 管理工具和内部对话。独立 Web 前端、FastAPI 服务与 CLI 共享同一 Agent 核心。

[架构与资料流](docs/architecture.md) · [能力与验收状态](docs/agent-capability-roadmap.md)

## 启动

仓库根目录 `.env` 的格式为 `DEEPSEEK_API_KEY=你的密钥`。`config/env.py` 使用固定仓库路径加载，禁止变量插值、保留现有环境变量，Web、CLI 和直接搜索调用共享配置。文件由 `.gitignore` 排除；本机已创建的文件权限为 0600，其他部署环境请自行设置文件权限。内容更新后重启服务。首次加载后搜索仍逐次读取当前进程环境，支持环境内轮换。

在仓库根目录执行。需要 Python 3.11+；联网搜索和默认聊天复用 `DEEPSEEK_API_KEY`。程序自动加载仓库根目录 `.env`，也支持维护人员设置进程环境变量；已有环境变量优先，不应把密钥写入 YAML、浏览器或 Git。

```bash
uv sync --project src
src/.venv/bin/python -m src.main                       # 默认 DeepSeek，Web 地址 127.0.0.1:8000
src/.venv/bin/python -m src.main --cli                 # 只显示最终答复的终端界面
src/.venv/bin/python -m src.main --port 8002
src/.venv/bin/python -m src.main --provider kimi       # 需要 MOONSHOT_API_KEY
src/.venv/bin/python -m src.main --provider local --model <model-name>
src/.venv/bin/python -m src.main --llm-config path/to/my-llm.yaml --provider my-provider
```

网页启动时加载 `.env`，但不创建模型，首条问题才加载模型配置；没有密钥也可预览界面。未配置模型时问题接口返回提示，不泄露配置路径或异常详情。CLI 在启动时加载模型。默认绑定 `127.0.0.1`，可通过 `--host` 指定已有受控部署的绑定地址。

当前为本地单用户应用，没有用户登录与权限隔离。原核心使用全局运行目录和附件会话状态，因此同一进程每次只处理一个问题；忙时返回重试提示，不应启用多个 workers。

## 产品与展示

`config/xiaochi.yaml` 管理产品名称、默认法域、服务场景、话术、快捷问题与免责声明。主提示词要求中文、礼貌简洁、结论在前，必要时列适用条件和官方依据，只询问影响答复的关键事实。正式报告与答复草稿使用 `config/output-contract.yaml` 和 `templates/report.md`，草稿须经工作人员审核。

普通咨询默认约 300 字。对于缺少主体、地区或资金条件的操作问题，先确认最多三项关键事实，再进行对应检索，不延伸用户未问的议题；明确要求政策原文、官方出处或详细分析时仍按需检索。

Web 与 CLI 都完整消费 Agent 运行，再从最后一个主 Agent 消息提取最终答复。工具调用结束、专家输出或仅思考的尾消息不能充当最终答复。每条最终答复由 `agent/public_answer.py` 统一追加 AI 生成提示。Web 不发送中间帧或内部推理事件；等待时按实际执行显示“小弛正在分析问题／检索官方政策／核对检索来源／整理答复……”及等待秒数。

前端每秒查询本轮 UUID 对应的进度接口，仅返回固定阶段、状态和耗时。`agent/progress.py` 使用请求上下文隔离通知，`web/progress.py` 保存最多 128 条内存快照，完成或失败即冻结；服务重启后快照清空，不作为持久化答复。接口不发送查询词、文件路径、专家内容或模型思考。

历史接口只返回公开消息及附件名称。旧记录通过公开投影恢复，过滤工具、思考和内联附件正文；模型继续使用完整的内部上下文。前端使用 `web/markdown.py` 统一渲染新答复与历史 Markdown，支持 `**中文：**①` 等中文标点边界的加粗；代码块和转义星号保留字面形式。禁用原始 HTML，保留政策链接并支持复制答复。

## 附件与持久化

支持 PDF、DOCX、表格、CSV 和文本等已注册格式。每条问题最多 5 个附件，单文件最多 25 MB。上传接口返回对话范围内的不透明 ID 与文件名，不接受客户端指定服务器路径。

- `workspace/conversations/<id>.json`：内部 `messages` 与公开 `public_messages`。均属服务器私有存储。
- `workspace/web_uploads/<conversation-id>/<upload-id>/`：上传原文件及名称元数据。
- `workspace/attachments/<document-id>/`：附件解析结果和定向回读索引。
- `workspace/<run-id>/`：日志、专家结果和能力轨迹。
- `reports/`：按请求生成的报告文件。

服务器仅挂载 `web/static/`，不暴露 workspace、日志或模型配置目录。附件先解析并内联或形成文档 ID；后续可通过 `AttachmentReadTool` 按页、工作表、行或关键词回读。点击新建对话不会删除已有记录。

## 模型与搜索

聊天配置位于 `config/llm.yaml`，默认 provider 为 `deepseek`。`--provider` 优先于 `LLM_PROVIDER` 和 YAML 默认值；`--model` 可覆盖模型 ID，`--llm-config` 可指向其他配置。provider 包含 `model`、`model_server`、`api_key_env`、`generate_cfg`。

本地模型可通过 SSH 隧道接入，例如 `ssh -N -L 11434:127.0.0.1:8000 <user>@<server>`，然后选择 `--provider local`。聊天选择其他模型时，联网搜索仍调用 DeepSeek，仍需其密钥。

### Web Search 配置

`WebSearchTool` 直接采用 DeepSeek Harness 的 `web-search-deepseek` 协议：
向 `https://api.deepseek.com/anthropic/v1/messages` 发起独立的 Messages 请求，
声明原生服务端工具 `web_search_20250305`。默认模型、输出上限和搜索次数与
[官方 Harness](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/web/web-search-deepseek)
一致。每次搜索消耗一个模型轮次，最多触发 5 次服务端搜索。

搜索与 DeepSeek 聊天共用 `DEEPSEEK_API_KEY`，每次请求从环境重新读取，因此密钥轮换
不需要重建客户端。聊天选择 Kimi 或本地模型时，联网搜索仍使用 DeepSeek。
搜索端点独立于聊天端点，不继承 `DEEPSEEK_BASE_URL`。

搜索请求使用 `output_config.effort=low`，官方 DeepSeek 路由的相关性判断使用 `reasoning_effort=low`，主回答保留聊天配置中的推理设置。参数见 [DeepSeek 推理模式说明](https://api-docs.deepseek.com/guides/thinking_mode/)。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 必需 | 与 DeepSeek 聊天使用同一密钥 |
| `DEEPSEEK_SEARCH_BASE_URL` | `https://api.deepseek.com/anthropic/v1` | HTTPS 搜索基址，自动追加 `/messages` |
| `DEEPSEEK_SEARCH_MODEL` | `deepseek-v4-flash` | 独立搜索模型，与 Harness 默认值一致，可显式覆盖 |
| `DEEPSEEK_SEARCH_EFFORT` | `low` | 搜索推理强度，支持 `low`、`high`、`max`；不改变主回答设置 |
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
`WebSearchTool` 自动读取相关官方 HTML 正文，返回 `source_text`、`source_url`、`source_title`、`source_read_at`、`source_sha256`、`source_truncated` 与 `source_status`；失败返回 `source_error`。`official_text_results` 和 `official_excerpt_results` 分别统计正文及引用摘录，两者都没有时标记 `leads_only`。

`websearch/sources.py` 每批并行读取至多三个官方候选，均失败时继续尝试后续候选；成功正文缓存 15 分钟、最多 128 条。每页 12 秒 HTTP 超时、2 MiB 下载上限，返回至多 16000 字符并标记截断。仅请求配置中的官方域名，跳转重新校验，拒绝内网地址和凭据 URL；网页请求不携带 DeepSeek 密钥。成功读取不代表政策仍然有效，Agent 仍须判断用户时点、适用对象和版本关系。

保留主 Agent 自主选择工具、专家和研究停止时点。已撤销三次共享网络预算和 URL-only 强制结束，保留原有每 Agent 15 次搜索保护及重复查询检查。官方域名配置位于 `config/jurisdictions.yaml`，搜索提供方统一为 `deepseek-official`。

DeepSeek HTTP 客户端遵循标准 HTTP(S) 代理环境变量。旧 OpenWebSearch daemon、
SearXNG 工具、SAFE 站内搜索及 WebFetchTool 已删除，不再读取旧 daemon／抓取配置。
上传 PDF 仍由附件摄取层解析，支持通过 `AttachmentReadTool` 按 `pdf:pN` 回读。

## 目录与接口

| 组件 | 文件与作用 |
|---|---|
| Agent 核心 | `agent/main_agent.py`、`agent/subagent.py`；自适应工具选择与可选专家 |
| 公开答复边界 | `agent/public_answer.py`；最终答复提取、旧记录过滤、统一提示语 |
| 会话执行 | `web/service.py`；串行执行、附件上下文、内部与公开持久化 |
| HTTP 接口 | `web/app.py`；会话列表、历史、新建、上传、最终答复 |
| 独立前端 | `web/static/`；HTML/CSS/JavaScript，无构建步骤或 CDN |
| 产品配置 | `config/xiaochi.yaml`、`config/product.py` |
| CLI | `agent/cli.py`；保留内部多轮上下文，公开最终答复 |
| 检索 | `websearch/` 与 `tools/web_search.py` |

只读接口包括 `GET /api/config`、`GET /api/conversations`、`GET /api/conversations/{id}` 及本轮 UUID 的进度接口。写接口为新建、上传、消息、`DELETE /api/conversations/{id}` 与 `POST /api/conversations/{id}/restore`。删除和恢复仅返回 ID 与状态，不返回内部上下文。删除采用 `.trash/` 可恢复记录，附件和运行日志保留；同一运行锁保护消息与历史管理，正在处理问题时返回 409。消息接口完整结束后一次返回 `answer` 与 `answer_html`，不支持过程流。

## 验证

先安装开发依赖，再运行离线测试：

```bash
uv sync --project src --extra dev
src/.venv/bin/python -m pytest -q src/tests
```

自动化测试包括多轮会话、历史投影、删除/撤销与运行互斥、附件隔离、最终答复提示、Markdown、进度与官方正文读取。199 项离线回归和八个真实场景通过，包含一项基于官方正文的政策回归；广泛税务政策质量及 42 题评测尚未完成。完整状态见能力路线图。

可复现真实模型迭代：

```bash
src/.venv/bin/python -m src.evals.xiaochi_smoke
```

该命令会调用 DeepSeek；使用独立临时会话，记录状态、答复、检查项、实际阶段和耗时到 `workspace/eval/xiaochi-smoke.json`，不记录密钥、请求头或完整模型配置，关闭后删除临时会话。检查覆盖身份、给定税率的纯算术、多轮改写、关键澄清、附件、官方链接定位及外籍个人分红公告的文件、文号、执行日期、适用对象、税率与旧条款废止。

原生搜索可能只有结构化链接，没有 `citations[].cited_text`。程序不把生成摘要或不透明 `encrypted_content` 当政策原文；官方 HTML 阅读补齐正文链路。外籍个人分红用例取得官方正文，完整回答 55.24 秒、四次搜索工具调用；此前简短缺口答复不能作为成功提速基准。远程 PDF、动态页面及长文定向回读尚未实现。
