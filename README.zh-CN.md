# 小弛 Agent

小弛基于 3wagent 的 Agent 核心，面向政府税务部门工作人员，辅助税收政策查询、办税材料解读、咨询答复草拟和税费计算。默认讨论中国内地事项；用户明确提出涉外情境时，再扩展其他法域。

[English](README.md) · [运行与配置](src/README.md) · [架构说明](src/docs/architecture.md) · [能力路线图](src/docs/agent-capability-roadmap.md)

## 主要功能

- 独立聊天界面：历史对话、新建对话、删除与撤销、附件上传、政策链接与答复复制。
- 政务蓝配色：深蓝品牌与主要操作、浅蓝背景与选中层次，红色用于少量强调和删除操作。
- 材料处理：支持 PDF、DOCX、表格、CSV 和文本等格式，每条问题最多 5 个附件，单文件最多 25 MB。
- 税务辅助：结论在前，按需补充适用条件和政策依据；信息不足时先询问最多三项关键事实。报告与答复草稿只按明确请求生成。
- 最终答复展示：Web 与 CLI 只显示完成后的答复。思考、工具调用、工具结果与专家中间文本留在后端，历史恢复同样过滤。
- 阶段进度：处理中显示“小弛正在检索官方政策……”等实际阶段及“已深度思考 xx 秒”，不展示思考正文或工具参数。
- 发送体验：提交后立即清空输入框；发送失败时恢复原文与换行，方便重试。

每条最终答复由程序统一追加：

> 以上内容由 AI 生成，仅供参考，具体请以现行有效政策及主管税务机关确认口径为准。

历史条目右侧提供删除按钮（桌面端悬停或键盘聚焦时显示，触屏端直接显示）。确认后移出历史列表，可点击“撤销”恢复。删除当前对话回到新对话，删除其他记录保留当前答复和草稿；生成答复时暂停历史管理。

## 快速开始

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。以下命令均在仓库根目录执行。

### 1. 配置密钥

创建根目录 `.env`，填入自己的 DeepSeek 密钥：

```dotenv
DEEPSEEK_API_KEY=your-deepseek-api-key
```

`.env` 和 `.env.*` 已被 Git 忽略。程序自动从固定仓库路径加载，无需额外执行 `export`；已设置的进程环境变量优先。修改 `.env` 后重启服务。真实密钥不应写入 README 或 YAML。

### 2. 安装并启动

```bash
uv sync --project src
src/.venv/bin/python -m src.main
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。默认聊天模型为 DeepSeek，聊天和原生联网搜索共用 `.env` 中的密钥。无需 Node.js、Docker 或搜索 daemon。

### 3. 其他启动方式

```bash
src/.venv/bin/python -m src.main --cli                 # 终端模式
src/.venv/bin/python -m src.main --port 8002           # 指定网页端口
src/.venv/bin/python -m src.main --provider kimi       # 需要 MOONSHOT_API_KEY
src/.venv/bin/python -m src.main --provider local      # 兼容 OpenAI API 的本地模型
```

聊天选择 Kimi 或本地模型时，联网搜索仍使用 DeepSeek，仍需 `DEEPSEEK_API_KEY`。更多模型、代理和搜索参数见[运行指南](src/README.md)。

## 架构与配置

```text
独立 HTML/CSS/JavaScript 前端
    → FastAPI → ChatService → MainAgent（qwen-agent）
        ├─ 附件解析与定向回读
        ├─ 配置及官方来源注册表
        ├─ DeepSeek 原生联网搜索
        └─ 按需调用专项专家
    → 最终答复提取与统一 AI 提示
```

原 Gradio 前端和旧搜索 daemon 已移除。Agent 继续复用内部多轮上下文、附件与可选专家能力；工具或专家调用没有固定流水线。

普通咨询默认约 300 字；缺少关键条件的操作问题先澄清，再做对应检索。搜索和 DeepSeek 相关性判断采用较低推理强度，主回答保留原推理设置。新答复与历史记录统一支持中文标点附近的 Markdown 加粗。

| 配置 | 用途 |
|---|---|
| [src/config/xiaochi.yaml](src/config/xiaochi.yaml) | 产品名称、默认法域、服务场景、话术、快捷问题与 AI 提示 |
| [src/config/llm.yaml](src/config/llm.yaml) | DeepSeek、Kimi、local 聊天模型配置 |
| [src/config/jurisdictions.yaml](src/config/jurisdictions.yaml) | 法域与官方来源域名策略 |
| [src/config/output-contract.yaml](src/config/output-contract.yaml) | 按请求生成的税务报告结构 |
| [src/templates/report.md](src/templates/report.md) | 税务报告和答复草稿模板 |

## 联网搜索与证据边界

搜索采用 DeepSeek Harness 的 `web-search-deepseek` 协议，调用 Messages API 的原生 `web_search_20250305`。仅接收结构化搜索来源和可关联到 URL 的引用摘录，不从模型生成的摘要中提取链接，也不回退 DuckDuckGo、Bing 或 SearXNG。

搜索返回后，`WebSearchTool` 自动读取相关官方 HTML 正文，交给 Agent 的结果包含原文、最终 URL、读取时间、哈希与截断标记。每批最多并行读取三个页面；失败时尝试其他官方候选。成功正文在进程内缓存 15 分钟。标题、链接与生成摘要本身不能作为政策条款依据。

保留主 Agent 自主选择工具和按需委派逻辑。已撤销三次共享检索上限与“仅有链接即强制结束”；停止条件仍是证据足够回答所问事项，进度提示只报告实际阶段。原有单 Agent 15 次搜索保护与重复查询检查保留。

**2026-10-07 实测：**外籍个人分红问题已取得官方正文，答复给出财政部 税务总局公告2026年第27号、2026年9月1日起执行、外籍个人从外商投资企业取得股息红利及20%税率，并说明旧条款废止。这是一项政策回归，不代表所有税务问题准确。

当前不支持远程 PDF、需要执行脚本的网页或本地法规正文索引。上传的 PDF 仍可按页回读。页面无法读取或原文未明确的事项会具体说明证据缺口。

## 测试与迭代

先安装开发依赖，再运行离线回归：

```bash
uv sync --project src --extra dev
src/.venv/bin/python -m pytest -q src/tests
```

显式运行真实 DeepSeek 行为测试：

```bash
src/.venv/bin/python -m src.evals.xiaochi_smoke
```

该命令会产生 API 用量，使用独立临时会话，报告写入 `src/workspace/eval/xiaochi-smoke.json`。报告不记录密钥、请求头或完整模型配置。

| 验证项 | 2026-10-07 结果 |
|---|---|
| 离线回归 | 199 项通过 |
| 真实模型测试 | 8/8 通过：身份、给定参数计算、多轮改写、税额澄清、跨境操作澄清、附件、官方链接定位、近期政策正式文件与适用范围核验 |
| 浏览器联调 | 桌面和移动端布局、等待提示、最终答复与历史恢复已检查；真实计算及中文加粗显示已验证 |

最新实测：购房问题首轮澄清 2.13 秒；官方链接定位 11.16 秒；外籍个人分红政策完整答复 55.24 秒、四次搜索工具调用。此前 16.22 秒的缺口答复没有完成用户任务，不能作为成功提速基准。政策回归现检查实际取得的正文，以及最终答复的文件名称、文号、执行日期、税率、适用对象和旧条款废止。

这八个样本验证产品行为及一项政策回归；完整 42 题和广泛税务政策质量验收仍未完成。各能力状态见[能力路线图](src/docs/agent-capability-roadmap.md)。

## 运行范围与数据

当前为本地单用户版本，默认绑定 `127.0.0.1`，没有账号与部门权限体系。原核心部分状态仍为进程全局变量，因此单个进程串行处理问题；多个 workers 尚不受支持。

对话、上传文件、解析结果与运行日志保存在 Git 忽略的 `src/workspace/`，按请求生成的报告位于 `src/reports/`。完整内部上下文与公开对话分别持久化；HTTP 接口只返回公开消息，静态路由不暴露 workspace 或模型配置。

对话删除采用可恢复的移除方式，记录移到会话目录的 `.trash/`；附件与运行日志保留，不作为彻底清除数据的功能。
