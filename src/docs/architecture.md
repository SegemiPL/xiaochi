# 小弛当前架构

本文描述 `src/` 中正在使用的运行时。小弛基于 3wagent 的核心，面向政府税务部门工作人员；历史跨境专项能力保留为按需专家。验收与未完成事项见[能力路线图](agent-capability-roadmap.md)。[SQLite FTS 文档](sqlite-fts-rag-plan.md)描述计划中的索引，尚未部署。

## 组件与边界

```text
浏览器：独立 HTML/CSS/JS 聊天页
    → FastAPI 接口（公开消息与最终答复）
        → ChatService（串行运行，附件与双份历史）
            → MainAgent（qwen-agent FnCallAgent）
                ├─ 附件解析与定向回读
                ├─ 配置及来源注册表读取
                ├─ WebSearchTool → DeepSeek Messages 原生搜索
                └─ 按需 DelegatePolicyTask → 专项 Agent

CLI → 同一 MainAgent → 最终答复边界
```

`src/main.py` 默认启动绑定 `127.0.0.1:8000` 的 FastAPI 服务，`--cli` 启动终端模式。`src/web/static/` 为无构建步骤的独立前端，原 Gradio 界面及依赖入口已删除。`src/config/llm.yaml` 默认选择 DeepSeek，也支持 Kimi 和本地兼容 OpenAI API 的模型。启动时自动加载仓库根目录 `.env`，已有环境变量优先；网页首条问题才创建模型。

搜索由 `src/websearch/deepseek.py` 调用 DeepSeek Anthropic 兼容 Messages API，使用 `web_search_20250305`，与聊天共用 `DEEPSEEK_API_KEY`。搜索端点独立于聊天模型和端点；没有 daemon、Node.js 或旧引擎回退。

`MainAgent` 统一使用 normal 模式，按问题与证据缺口选择工具。普通问题直接回答；复杂事项可委派来源检索、有效性、税务或引用复核。涉外问题可按需使用资金合规和民商法专家，默认不扩展其他法域。主 Agent 获得北京时间的当前日期，用户指定的所属期独立遵守。代码不强制固定研究流水线。

## 用户答复与内部执行

`web/service.py` 完整消费 Agent 的所有帧后，才由 `agent/public_answer.py` 提取最后一个主 Agent 的最终正文。思考字段、工具调用及响应、专家输出不进入 HTTP 响应；只剩工具、专家或思考的未完成尾帧返回通用未完成提示，不把先前规划当成结论。嵌入式思考块也会过滤。CLI 复用同一边界。

每条最终答复由程序统一追加 `config/xiaochi.yaml` 中的 AI 生成提示。前端按本轮 UUID 每秒查询固定阶段与耗时，显示“小弛正在检索官方政策……”等实际进度，收到最终答复后停止轮询、一次展示正文。`agent/progress.py` 隔离通知上下文，`web/progress.py` 的有界快照只含阶段、状态与耗时。服务端 Markdown 禁用原始 HTML，支持中文书名号附近加粗；客户端不拿内部消息进行 CSS 隐藏。

计时展示文案为“已深度思考 xx 秒”，仍统计本轮处理耗时。有效提交时前端先保存草稿、立即清空输入框并复位高度；消息请求失败则恢复原文字、空白、换行和高度。消息已成功但历史刷新失败时不恢复草稿，避免误导用户重复发送。

`web/static/style.css` 用主题变量统一政务蓝配色：深蓝主色、蓝灰正文、浅蓝背景/选中状态，红色用于少量强调及删除；`index.html` 的浏览器主题色与 `favicon.svg` 同步。桌面与手机布局复用同一配色。

`ConversationStore` 保存内部 `messages` 与独立 `public_messages`。API 使用白名单返回公开问题、答复及附件名称，历史标题也从公开内容计算。旧记录通过投影过滤工具、思考及内联附件正文；内部上下文保留供后续问题使用。API 和静态文件路由不挂载日志、workspace 或配置目录。

历史删除将会话 JSON 原子移入 `.trash/`，活动历史和读取接口不再返回；撤销将原记录移回，内部上下文及附件保持可用。删除/恢复和 Agent 执行共用运行锁，生成中不接受历史管理；前端确认后删除，并提供撤销。删除当前对话清除当前 ID，删除其他记录保留当前答复及草稿。此功能不清除附件、解析缓存或运行日志。

## 资料与证据

上传文件以对话内的不透明 ID 引用，接口不接受服务器路径。附件解析器将可读取正文内联到内部上下文；较大的文件通过文档 ID、页码、工作表或行范围回读。旧轮附件 ID 会在本轮恢复注册。原文件和解析结果均不作为公开历史返回。附件内容和搜索摘录作为证据而非指令。

`WebSearchTool` 使用来源注册表推断权威域名，默认中国内地；只接受结构化 `web_search_tool_result` 的 URL，模型生成正文不作搜索结果。`websearch/sources.py` 自动读取相关官方 HTML 正文，每批三个页面并行，失败换其他候选；成功结果在有界内存缓存 15 分钟。返回正文、最终 URL、时间、哈希和截断标记，网页请求不携带 API 密钥。正文与引用摘录分别计数；仅有链接仍为 `leads_only`，但不会强制结束 Agent。正文读取不等于现行有效性核验；版本、时点和适用对象仍由原 Agent 判断。没有远程 PDF、动态页面处理、本地正文索引或完整结构化证据账本。

产品场景与话术在 `config/xiaochi.yaml`，领域策略在 `config/*.yaml`，提示词在 `prompts/`。`config/output-contract.yaml` 与 `templates/report.md` 只用于明确要求的税务报告或答复草稿，列出范围、结论、适用条件、政策依据及待确认事项，按需补充计算、案例或沿革。

主 Agent 保留原来的 normal 模式、自主工具选择和按需专家委派。撤销新增的三次共享预算和 URL-only 强制终止；原有每 Agent 15 次搜索保护、重复查询检查与合法终止结果收尾保留。流程缩减依靠复用已取得的正文、不扩展无关问题、证据足够即停止；阶段通知不参与工具选择。

## 持久化与并发

- `workspace/conversations/<id>.json`：完整内部与公开会话，供历史恢复和继续提问。
- `workspace/web_uploads/<conversation-id>/<upload-id>/`：原始上传文件与名称元数据。
- `workspace/attachments/<document-id>/`：解析结果及回读索引。
- `workspace/<run-id>/`：日志、专家结果与能力轨迹。
- `reports/`：按请求生成的报告文件。

当前是无账号体系的本地单用户应用。由于运行目录和附件会话仍是进程全局状态，`ChatService` 使用非阻塞互斥锁串行执行问题，忙时返回 409；不支持多个 workers。单轮失败不保存部分公开对话，客户端返回通用错误，详细异常只留在服务器。上述目录不代表法规不可变快照库。

## 迭代评测

`src/evals/xiaochi_smoke.py` 是显式运行的真实 DeepSeek 行为评测，不进入默认离线测试。八个真实场景通过实际 HTTP 接口验证最终输出、AI 提示、内部字段隔离、纯计算、多轮改写、关键事实澄清、附件、官方定位和一项政策原文回归，结果保存于 `workspace/eval/xiaochi-smoke.json`。已有 8/8 通过证据；一项政策回归不代表广泛税务政策质量或完整 42 题验收。
