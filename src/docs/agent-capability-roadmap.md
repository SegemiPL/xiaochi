# 小弛（基于 3wagent）能力改进与实现状态

## 1. 文档目的

本文档将 `Dem测试问题(1).pages` 中的 42 道候选题转化为可实施、可验收、可持续更新的能力路线图。

测试文件中的问题、日期、资料编号和资料状态均视为评测样本，不因写入本文档而成为已经核实的法律事实。正式实现和验收仍须使用实际取得的官方材料。

本文档与 [`sqlite-fts-rag-plan.md`](sqlite-fts-rag-plan.md) 的关系：

- 本文档定义面向最终用户的整体能力和优先级；
- SQLite FTS 文档定义本地法规知识库与检索层的技术方案；
- 两者重叠时，以本文档的验收目标为准，以专项技术文档描述具体实现。

## 2. 维护规则

凡实现、部分实现、重新设计或取消本文档中的能力项，必须在同一次工作中：

1. 更新状态和“最后更新”；
2. 在“实现证据”中写明代码、测试或评测文件；
3. 对照验收标准，不满足全部标准不得标记为“已完成”；
4. 在文末“实现记录”追加一条简短记录；
5. 不因无关的修复或重构改动本文档。

状态定义：

| 状态 | 含义 |
|---|---|
| ✅ 已完成 | 验收标准全部满足，并有自动化测试或等价证据 |
| 🟡 部分实现 | 已有可用基础，但仍不能覆盖相应测试场景 |
| 🚧 进行中 | 当前工作正在实现，尚未完成验收 |
| ⬜ 未开始 | 尚无针对性实现 |
| ⛔ 阻塞 | 存在明确外部依赖，记录阻塞原因和解除条件 |

## 3. 测试题能力地图

| 题组 | 数量 | 核心能力 | 主要验收重点 |
|---|---:|---|---|
| A：基础查询与横向覆盖 | 12 | 原文定位、官方来源、来源类型、限定输出、多语言 | 条款准确、引用可回查、不扩展范围、遵守长度和语言要求 |
| B：比较、追溯与专题分析 | 4 | 历史沿革、跨部门衔接、专业解读核验、增量更新 | 新旧版本关系准确，仅更新受影响结论 |
| C：离岸信托 | 10 | 生命周期、角色、税务与外汇交叉、计算、多轮跨法域 | 明示关键事实、条件分支、阶段分析、未决问题 |
| D：外籍个人分红 | 10 | 身份分支、协定、时间边界、居民地处理、税额计算 | 区分个人/公司、国籍/税收居民、来源地/居民地和抵免 |
| E：特殊情况 | 6 | 错误前提、信息不足、无结果、重复版本、改写、引用回查 | 不顺从错误前提，最小澄清，诚实报告缺口，多轮一致性 |

## 4. 当前能力基线

| 编号 | 能力 | 状态 | 最后更新 | 实现证据与缺口 |
|---|---|---|---|---|
| BASE-01 | 来源注册表辅助、DeepSeek 原生搜索、相关性过滤与官方域有界重试 | 🟡 部分实现 | 2026-10-07 | `src/websearch/deepseek.py`、`src/tools/web_search.py`、`src/tests/test_deepseek_search.py`、`src/tests/test_search_strategy.py`；Messages 原生搜索复用密钥，保留相关性判断、官方域重试、原有每 Agent 15 次搜索保护和重复检查。撤销新增三次共享预算及 URL-only 强制结束，保留自主工具选择和按需委派。`src/websearch/sources.py` 为相关官方结果补齐 HTML 正文，分别统计正文及摘录。真实政策回归取得正文并正确回答文号、日期、范围、税率及废止关系，55.24 秒、四次工具搜索；42 题和广泛政策质量验收仍未完成 |
| BASE-02 | 官方 URL 来源追踪与 HTML 正文读取 | 🟡 部分实现 | 2026-10-07 | `src/websearch/provenance.py`、`src/websearch/sources.py`、`src/tests/test_official_sources.py`、`src/tests/test_web_search_integration.py`；只读取 DeepSeek 发现的相关官方 HTML，返回正文、最终 URL、时间、哈希和截断标记；并行读取、失败换官方候选、15 分钟有界缓存。测试覆盖财政部/税务页面结构、中文编码、403、跳转/域名边界、缓存、缺正文和大小限制。未恢复旧 daemon/tool/远程 PDF；尚无持久快照、分块和定向回读 |
| BASE-03 | 附件解析与定位 | 🟡 部分实现 | 2026-09-11 | 支持 PDF、DOCX、Excel、CSV、文本；不支持 Pages，复杂远程文件没有统一缓存索引 |
| BASE-04 | 对话持久化 | 🟡 部分实现 | 2026-10-07 | `src/agent/conversations.py` 保存内部与公开上下文，并支持移入 `.trash/` 删除和撤销恢复；`src/web/service.py`、`src/web/app.py` 对历史管理与运行互斥，API 仅返回公开记录；`src/tests/test_conversations.py`、`src/tests/test_xiaochi_web.py` 验证重启后仍删除、恢复原上下文/附件、其他记录不变及运行锁。尚未保存结构化事实、结论、来源和计算状态 |
| BASE-05 | 来源有效性与引用核验子代理 | 🟡 部分实现 | 2026-09-11 | 已有 Validate/Citation Verifier；主要处理 Markdown，尚无 claim-source 结构化契约 |
| BASE-06 | CLI、独立 Web 前端与多模型兼容 | ✅ 已完成 | 2026-10-12 | 删除 Gradio 前端；`src/web/app.py`、`src/web/static/` 提供 FastAPI 与独立聊天页；`src/agent/public_answer.py`、`src/agent/cli.py` 统一只展示最终答复及 AI 提示；默认 DeepSeek，保留 Kimi/local；`src/tests/test_cli.py`、`src/tests/test_llm_config.py`、`src/tests/test_xiaochi_web.py`、`src/tests/test_web_search_integration.py` 覆盖接口与启动；`src/web/markdown.py` 与 `src/tests/test_markdown.py` 修复中文标点边界加粗，接口覆盖新答复和历史一致渲染；浏览器确认原问题及书名号开头的加粗标签为 strong、字重 700；`src/agent/progress.py`、`src/web/progress.py` 与前端提供真实阶段和耗时，194 项回归及浏览器检索进度/完成恢复检查通过；浏览器完成 1280×900/390×844 布局、等待与历史恢复验证（截图 `src/workspace/preview/`）。真实模型端到端质量验收仍记录在 BASE-01/CAP-01，不据界面通过推定完成；ASR/TTS 保留：原生麦克风、结论口播、首句预生成与分段播放，见 `src/web/voice.py`、`src/web/static/voice.js`。 `src/voice/text.py`、`narration.py`、`client.py` 过滤仅展示的 AI 尾注，输入/模型输出/缓存/分段边界回归见 `src/tests/test_voice_narration.py`，220项测试通过；真实 DeepSeek/Fish 测试音频及口播文本见 `src/workspace/eval/voice-footer-2026-10-12.*`。 |

### 小弛产品重构（2026-10-07）

| 编号 | 能力 | 状态 | 最后更新 | 实现证据与验收边界 |
|---|---|---|---|---|
| XIAOCHI-01 | 独立税务聊天前端 | ✅ 已完成 | 2026-10-12 | `src/web/static/index.html`、`style.css`、`app.js`：深蓝侧栏、浅蓝咨询区、红色业务图标/标题强调和 SVG 资料装饰；入场、悬停、聚焦、蓝色等待转圈及录音状态动效，系统减少动态效果时全部停用。历史/附件/复制/三个推荐保留，删除提示8秒自动收起。浏览器检查1280px桌面、1024px平板、390px手机无横向溢出、首页卡片和输入区不重叠，业务入口/推荐填入与历史恢复正常；截图 `src/workspace/preview/xiaochi-blue-red-home.jpg`、`xiaochi-blue-red-answer.jpg`、`xiaochi-blue-red-mobile.jpg`。图标来源见 `src/web/static/icons/`，删除提示证据见实现记录 按浏览器反馈移除历史红边、品牌红线及右侧卡片顶部蓝红线；官方入口图标新增悬停/键盘聚焦抬起、缩放与扫光，验证截图 `src/workspace/preview/xiaochi-clean-accents.jpg`。 首页顶部与栏目标签装饰线移除；等待转圈与阶段/耗时并列，独立模拟预览证据 `src/workspace/preview/xiaochi-home-no-topline.jpg`、`xiaochi-waiting-spinner.jpg`。 侧栏新增用户参考形象生成的动态 Q 版小人，素材/样式/来源见 `src/web/static/mascot/`，状态接入 `app.js`；眨眼、挥手、忙碌恢复、后台/手机侧栏暂停及减少动态效果通过浏览器检查，1280/1024/390px 无溢出，17项 Web 测试通过；证据 `src/workspace/preview/xiaochi-mascot-check.json`。 首页新增税收/外汇/商务发改三类十二项入口、外汇局/发改委官方图标；输入框约190px高，移除上方标题与底部重复提示。1412/1024/390px无溢出与重叠，切换保留草稿、事项填入及历史恢复正常；证据 `src/workspace/preview/xiaochi-business-home.jpg`、`xiaochi-business-mobile.jpg`。 小人放大25%，通过帧间裁切修复挥手时头顶漏出的上一行鞋底，四帧及桌面/平板/手机复验见同检查记录。 |
| XIAOCHI-02 | 税务部门角色、业务配置与报告模板 | 🟡 部分实现 | 2026-10-12 | `src/config/xiaochi.yaml`、`src/prompts/prompts.py` 与报告契约/模板；默认中国内地、结论在前、缺少条件先澄清。正确性与完整性优先，政策答案长度服从所需条件，不为提速强制拒答。`src/evals/xiaochi_smoke.py` 八个真实场景通过，含外籍个人分红正式文件、文号、执行日期、适用范围、税率和旧条款废止核验；一项政策回归不足以完成全面税务质量验收，参考站未成功加载 `business_categories` 与 `web/app.py` 增加三类业务入口配置，前端验证类别及草稿，不据此升级外汇/商务发改业务准确性验收。 |
| XIAOCHI-03 | 最终答复展示与统一 AI 提示 | ✅ 已完成 | 2026-10-12 | `src/agent/public_answer.py`、`src/web/service.py`、`src/agent/conversations.py`、`src/agent/cli.py`；含思考/工具/专家输出的模拟 agent 验证后端不发送过程，恢复历史同样投影，提示语只追加一次；公开进度仅返回固定阶段、状态与耗时，UUID 区分请求并禁止跨对话查询，完成或失败冻结；`src/tests/test_progress.py`、`src/tests/test_public_answer.py`、`src/tests/test_xiaochi_web.py`、`src/tests/test_cli.py`，浏览器验证等待及最终答复；`followups.py` 与 `test_followups.py` 验证推荐元数据不进入正文，非法/截断区块不暴露，思考/工具/专家不能提供推荐 答复末尾统一提示保留，移除输入框下方重复提示，语音排除该尾注；`src/tests/test_voice_narration.py` 验证公开正文/HTML仍含提示、口播及TTS文本不含提示，业务限制保留。 |
| XIAOCHI-04 | 本地 .env 加载与密钥隔离 | ✅ 已完成 | 2026-10-12 | `src/config/env.py` 固定仓库路径加载私有 `.env`、环境变量优先；聊天和搜索共享加载；`.gitignore` 覆盖且本机文件为 0600；`src/tests/test_env.py` 验证路径、优先级、共享凭据及缺失文件；真实调用验证成功，代码、报告及运行日志扫描未发现密钥值；部署模板 `.env.example` 仅含空凭据字段，`.gitignore` 显式允许模板并继续忽略私有环境文件；中英文 README 与运行/语音文档说明固定加载路径、环境优先级、密钥文件入口及 ASR 不加载 `.env` 的边界。环境与模型配置8项回归通过，启动帮助与无外部调用的配置检查通过 |
| XIAOCHI-05 | 每轮三个相关问题 | ✅ 已完成 | 2026-10-08 | `src/agent/followups.py`、`public_answer.py`、`src/web/service.py`、`static/app.js`：同轮生成、严格校验、按场景兜底、公开历史持久化；不增加独立模型请求或工具流程。`src/tests/test_followups.py` 与 `test_xiaochi_web.py` 覆盖异常元数据、内部信息隔离、新答复/恢复/删除撤销；真实计算和虚拟材料两项均返回模型生成的三个问题，点击填入及刷新一致。广泛推荐质量仍需后续样本迭代 |

这里的完成状态仅针对所述界面与输出边界；当前是串行执行的本地单用户应用，账号、部门权限与多人部署不在本轮验收范围。

## 5. 待实现能力

### CAP-01：自适应任务编排

- **优先级：P0**
- **状态：🟡 部分实现**
- **最后更新：2026-10-07**
- **覆盖题目：A01–A12、D08、E05、E06，以及所有短问**

目标：所有问题继续使用 normal 模式，由主 agent 根据任务复杂度自主选择能力；子代理按需调用，不再让所有政策问题固定经过完整流水线。

待办：

- [x] 将固定的 Routing → RAG → Validate → Analyst → Citation → Report 流程改为可选能力调用。
- [x] 短问、纯原文定位、纯计算和改写任务可直接完成。
- [x] 跨法域、历史沿革、复杂核验时允许主 agent 调用一个或多个专家。
- [x] 以“证据是否足够回答用户问题”作为停止条件。
- [x] 记录选择了哪些能力及原因，供调试使用，但不强制暴露给最终用户。

验收标准：

- A02、A04 不运行无关的类案和全面沿革检索；
- A08 输出不超过用户要求的 300 字；
- D08 不触发法规检索；
- E05 复用上轮研究，仅改变表达方式；
- 复杂问题仍能主动使用检索、有效性核验和专业分析。

实现证据：`src/agent/main_agent.py` 删除政策问题模式检测和固定流水线，所有输入统一进入 normal 模式主 agent；`src/tools/delegate_policy_task.py` 提供无前置顺序、单任务边界的可选专家委派（工具描述直接列出合法 capability 名，避免模型猜测浪费轮次）；`src/prompts/prompts.py` 定义最小能力集合、停止条件、短问/计算/改写直答和复杂问题分解原则；`workspace/<run-id>/capability_trace.jsonl` 记录工具、专家能力和选择原因；`src/tests/test_adaptive_orchestration.py` 覆盖 normal 模式、单专家隔离、错误能力拒绝和调试轨迹，`src/tests/test_web_search_integration.py` 覆盖主 agent 工具能力与自适应提示契约。2026-09-12 两轮 22 个真实模型 CLI 用例（覆盖 A–E 五类）显示委派决策方向全部正确，但尚未形成结构化 smoke eval；完成 CAP-01 smoke eval 前维持"部分实现"。

补充评测：`src/evals/xiaochi_smoke.py` 八个真实场景通过，简单算术、附件、改写和跨境澄清不触发无关检索；政策问题保留自主研究并取得官方正文。已撤销新增的共享预算和 URL-only 强制收尾，进度通知只观察执行阶段。该样本尚不覆盖全部 A–E 验收标准，状态保持部分实现。

### CAP-02：回答约束、错误前提与最小澄清

- **优先级：P0**
- **状态：🟡 部分实现**
- **最后更新：2026-10-07**
- **覆盖题目：A02、A05、A08、A10、E01–E03、E05**

目标：研究前抽取用户的范围、日期、字数、语言、引用、计算和禁止扩展要求；区分事实、假设、用户主张和待核实前提。

待办：

- [ ] 建立结构化 `AnswerContract`，包含截止日期、范围、长度、语言、引用和计算要求。
- [ ] 对明显错误或未经证实的前提先纠正或降级，不顺着前提计算。
- [ ] 信息不足时只询问最高信息增益的关键事实。
- [ ] 支持“仅解释原文”“不判断具体产品”“暂不计算”等负面范围约束。
- [ ] 无可靠结果时明确资料缺口和下一步入口，不补凑结论。

验收标准：E01 拒绝“统一按20%”的错误概括；E02 先确认法域、资产与角色；E03 不用无关资料填充；所有限字和不扩展要求得到遵守。

实现证据：`src/config/xiaochi.yaml` 和 `src/prompts/prompts.py` 增加税务部门场景、首轮最多三项关键事实澄清、区分政策/推论/草稿与简洁答复；`src/tests/test_xiaochi_web.py` 验证身份与默认法域，`src/evals/xiaochi_smoke.py` 的真实 missing_facts 与 cross_border_clarification 场景通过，未列未经核实税率；增加普通咨询约 300 字及不扩展未问事项的约束。购房问题先询问身份、地区和资金条件，2.34 秒、无检索工具调用；这一变化缩小首轮范围，不代表完整政策分析等深度加速。尚无结构化 AnswerContract 或完整错误前提/限字评测，保持部分实现。

2026-10-07 纠正：政策解释不能以缺口短答代替可查得的结论。提示词要求读取官方正文，失败换同文件其他官方来源，再报告具体缺口；正文长短服从正确性和适用条件。评测不再将拒答算成功，新增正式文件、执行日期、主体范围、税率及废止关系断言；用户政策问句真实通过。完整约束和错误前提题组仍待验收。

### CAP-03：结构化证据账本与结论级引用

- **优先级：P0**
- **状态：⬜ 未开始**
- **最后更新：2026-09-12**
- **覆盖题目：全部；重点 B03、B04、E04、E06**

目标：使用结构化 `Claim`、`Source`、`EvidenceSpan` 和 `Inference`，替代仅靠 Markdown 在代理之间传递证据。

最低数据字段：

- claim id、结论、法域、主体、事实条件和适用日期；
- 来源类型、权威机关、URL、版本和有效状态；
- 页码、条款、段落定位和短原文；
- 结论是直接规定、合理推论、专业解释还是未决判断；
- 可靠性、冲突来源和缺失事实。

待办：

- [ ] 定义可版本化的数据模型和 JSON Schema。
- [ ] Retrieval 输出 `EvidencePack`，分析输出 `ClaimSet`。
- [ ] Citation Verifier 逐 claim 验证，而不是只审核整篇 Markdown。
- [ ] Report Writer 仅消费验证后的 claim。
- [ ] 对每条关键结论提供可回查的原文定位。

验收标准：E06 能逐条给出原文支持；B03 能区分直接规定、作者解释和争议判断；缺少直接支持时自动降低结论等级。

实现证据：待补充。可复用 `sqlite-fts-rag-plan.md` 中的 EvidencePack 设计。

### CAP-04：远程文档缓存、分块索引与定向回读

- **优先级：P0**
- **状态：🟡 部分实现**
- **最后更新：2026-10-07**
- **覆盖题目：A03–A06、A09、A10、A12、B01、C06、R09、R16、R18、R28、R30**

当前范围说明：旧抓取工具和 daemon 已移除；2026-10-07 在 DeepSeek 搜索结果内部增加官方 HTML 读取和 15 分钟有界内存缓存。尚无持久不可变快照、远程 PDF、分块索引或定向回读，不能视为本项验收完成。

目标：远程 HTML/PDF 第一次抓取后保存不可变快照并分块，后续按页码、条款、标题、关键词或相邻段落读取本地缓存。

待办：

- [ ] 保存正文、内容哈希、抓取时间、最终 URL、MIME 类型和解析器版本。
- [ ] HTML 按标题/段落切分，PDF 保留页码。
- [ ] 提供 `source_id + locator/query` 的定向读取接口。
- [ ] 同一 URL 后续读取走缓存，而不是禁止读取或重复联网。
- [ ] 识别发布页附件、议定书、多文件汇编和站内导航关系。
- [ ] 为动态页面、403 和正文抽取失败提供有界降级，并标记获取方式。

验收标准：长篇 HMRC、EUR-Lex、协定汇编和资本项目指引可读取任意相关章节；引用保留稳定页码/条款；8,000 字上下文限制不再造成内容永久不可见。

实现证据：`src/websearch/sources.py` 返回正文、哈希、读取时间、最终 URL 和截断标记，缓存重复读取，正文提取失败时保留原因并换官方候选；`src/tests/test_official_sources.py` 验证缓存、失败回退、编码、大小和文章来源结构；`src/evals/xiaochi_smoke.py` 验证真实官方正文取得。长文任意章节回读与稳定定位仍未实现，技术方案见 `sqlite-fts-rag-plan.md`。

### CAP-05：动态法域与来源覆盖

- **优先级：P1**
- **状态：🟡 部分实现**
- **最后更新：2026-09-12**
- **覆盖题目：A07–A12、C08、C09、D05–D10、E03**

目标：法域、官方域名和来源注册表由配置动态加载，工具 schema 不再静态限制为 CN/US/HK/SG。

待办：

- [ ] 增加 UK、AU、EU 法域配置和来源注册表。
- [ ] 补齐 HMRC、ATO、EUR-Lex 等官方域名与来源类型。
- [ ] 支持中国地方税务来源及城市/省级隶属关系。
- [ ] 从配置生成或宽松校验 WebSearch 的法域参数。
- [ ] 对未知法域允许模型搜索并返回“未配置”，而不是 schema 层拒绝。

验收标准：A10、A12、D07、D09、E03 可以使用正确法域过滤和官方来源识别；新增法域无需修改 Python 枚举。

实现证据：当前仅有 `cn.yaml`、`us.yaml`、`hk.yaml`、`sg.yaml`。

### CAP-06：时点适用与法规版本关系图

- **优先级：P1**
- **状态：🟡 部分实现**
- **最后更新：2026-09-12**
- **覆盖题目：A01、A07、B01、B03、B04、C03、C07、D01、D02、D04、E04**

目标：区分发布、公布、生效、废止、交易、支付、申报和用户截止日期；保存修改、替代、废止、解释、转载关系及其作用范围。

待办：

- [ ] 建立带时间区间的 `SourceVersion` 和 `SourceRelation`。
- [ ] 支持条款级修改，而非只记录整份文件“已修改”。
- [ ] 根据事实发生日和用户的 as-of date 选择适用版本。
- [ ] 区分正式规定、问答、新闻稿、解释材料、地方转载和法规库镜像。
- [ ] 对无法确认的有效性保持未知，不自动标记“现行有效”。

验收标准：B01 可生成有官方依据的单层或多层时间线；D04 能说明决议日和支付日各自是否具有规范意义；E04 能去重并解释不同时间口径。

实现证据：来源 schema 已预留日期、状态和 `amended_from` 字段，Validate prompt 已有基础，但尚无关系图和确定性版本选择。

### CAP-07：跨法域、跨部门与生命周期分析

- **优先级：P1**
- **状态：🟡 部分实现**
- **最后更新：2026-09-12**
- **覆盖题目：B02、C02–C05、C07–C10、D03、D05–D07、D09、D10**

目标：围绕统一事实模型，按比较轴和生命周期分析多个法域/部门，而不是拼接各分析师摘要。

比较轴至少包括：主体及角色、国籍、税收居民、外汇身份、所得归属、来源地税、居民地税、协定资格、抵免/豁免、分配和申报时点。

待办：

- [ ] 建立人物、实体、资产、交易、控制、受益和时间事件的事实图。
- [ ] 为信托建立设立、装入、存续、分配、变更/终止阶段。
- [ ] 每个“法域 × 比较轴”单元绑定来源和缺失事实。
- [ ] 支持证监会备案与外汇登记等不同制度的适用条件和衔接点。
- [ ] 将国籍、税收居民身份和外汇管理身份明确分离。

验收标准：C04 不混淆不同身份概念；C09、D09 形成逐法域可核验矩阵；B02 不把不同制度误写成同一审批流程。

实现证据：当前 tax/funds/commercial 分析师可分别分析，但缺少共享事实模型和矩阵契约。

### CAP-08：确定性计算与可复核公式

- **优先级：P1**
- **状态：⬜ 未开始**
- **最后更新：2026-09-12**
- **覆盖题目：C06、D05、D08，以及涉及税额/净额的后续问题**

目标：法律参数由证据确定，算术由通用计算能力执行并保留公式、变量、币种、期间和舍入规则。

待办：

- [ ] 增加安全、确定性的计算接口，不执行任意代码。
- [ ] 区分题目给定参数、来源参数和模型推导参数。
- [ ] 输出逐步公式和交叉校验。
- [ ] 支持情景分支，不将未知税率默认为零或固定值。
- [ ] 保存计算输入和输出，供多轮调整复用。

验收标准：D08 稳定得到抵免 15,000、居民地剩余税额 15,000、两地合计 35,000；D05 可复核两地税款与税后净额；C06 明确费用能否扣除是法律判断而非算术假设。

实现证据：待补充。

### CAP-09：会话研究档案与增量更新

- **优先级：P1**
- **状态：🟡 部分实现**
- **最后更新：2026-09-12**
- **覆盖题目：B04、C08–C10、D10、E05、E06**

目标：会话除消息外，还保存结构化事实、claim、来源版本、未决问题和计算状态；后续问题只重做受变化影响的部分。

待办：

- [ ] 建立 conversation-level research dossier。
- [ ] 对新消息计算事实和材料差异。
- [ ] 建立“变更 → 受影响 claim/法域/计算”的依赖关系。
- [ ] 支持仅改写、不重新研究。
- [ ] 新材料无法支持旧结论时，明确保持、降级或撤回。

验收标准：C08 只增加美国公民身份相关分析；D10 只重做英国居民地分支；B04 明确哪些结论不变、哪些需要重研；E05 不重复调用网络。

实现证据：已有 JSON 会话消息存储，尚无研究档案。

### CAP-10：多语言法规对齐

- **优先级：P2**
- **状态：⬜ 未开始**
- **最后更新：2026-09-12**
- **覆盖题目：A08、A10、A12，以及境外材料**

目标：保留原语言限定词、条款编号和位置，同时提供忠实中文解释；同一法规的多语言官方文本可以条款级对齐。

待办：

- [ ] 保存文档语言和官方语言版本关系。
- [ ] 按 article/paragraph/item 对齐 EUR-Lex 等平行文本。
- [ ] 短引文保留原文，解释与翻译明确分离。
- [ ] 检测翻译可能改变法律含义的限定词并提示人工复核。

验收标准：A12 同时给出 Article 3(1) 的英文、法文定位和中文解释；A10 保留 HMRC 的关键英文限定条件。

实现证据：待补充。

### CAP-11：42 题自动化评测集

- **优先级：P0（贯穿实施）**
- **状态：⬜ 未开始**
- **最后更新：2026-09-12**
- **覆盖题目：全部**

目标：把测试题转成结构化 eval，而不是为每题硬编码答案。

待办：

- [ ] 将题目、基础事实、截止日期、资料编号和输出约束转换为 JSONL/YAML。
- [ ] 为每题定义能力标签和分项 rubric。
- [ ] 区分离线固定快照评测与在线最新来源评测。
- [ ] 建立小型 smoke 集、完整回归集和多轮会话集。
- [ ] 记录模型、provider、token、工具调用、耗时、失败原因和最终得分。
- [ ] 对搜索、抓取、推理、引用、计算和表达分别评分。

核心指标：

- 官方来源命中率和无关结果率；
- claim 级证据支持率、原文定位准确率；
- 版本和截止日期适用准确率；
- 用户范围、限字和语言要求遵守率；
- 错误前提纠正和资料缺口诚实度；
- 计算正确率；
- 多轮事实保持和增量更新正确率；
- 工具调用数、重复调用数、token、延迟和异常率。

验收标准：每项能力改动至少关联一个失败前用例和通过后用例；不得仅以“最终答案看起来合理”判定完成。

实现证据：`src/tests/test_search_strategy.py` 已为搜索噪声建立代码级回归，但尚未转换 42 题。

## 6. 建议实施顺序

| 阶段 | 内容 | 退出条件 |
|---|---|---|
| 0 | 搜索质量基线 | DeepSeek 原生搜索、注册表权威域推断、相关性过滤、官方域重试和提供方错误处理进入稳定分支并完成实测 |
| 1 | CAP-01、CAP-02、CAP-11 smoke 集 | 短问、纯计算、错误前提和限字任务不再进入固定长流程 |
| 2 | CAP-03、CAP-04 | 结论可回查到缓存文档的具体页码/条款，长文档可定向回读 |
| 3 | CAP-05、CAP-06、CAP-10 | UK/AU/EU 可检索；多语言和历史版本可选择、可核验 |
| 4 | CAP-07、CAP-08、CAP-09 | 跨法域矩阵、确定性计算和多轮增量更新通过对应题组 |
| 5 | 完整 42 题回归 | 核心指标达到约定阈值，并能跨模型/provider 重复运行 |

## 7. 实现记录

按时间倒序追加。每条记录应关联能力编号、代码或测试证据，并说明状态变化。

### 2026-10-07

- `BASE-06`：启动入口不再依赖本地搜索后台服务；完整回归发现原有侧栏 `gfm-like` Markdown 渲染缺少链接识别组件，在 Python 与 conda 依赖清单补充 `markdown-it-py[linkify]`，保持现有展示行为。验证由 `src/tests/test_webui_display.py` 和入口集成用例覆盖，完整回归 148 项通过。

- `BASE-01`、`BASE-02`：联网搜索切换到 DeepSeek Harness `web-search-deepseek` 使用的 Anthropic 兼容 Messages 协议，复用 `DEEPSEEK_API_KEY`。新增原生结构化结果、引用摘录、来源日期、去重与截断、无搜索块拒绝、HTTP/工具错误、凭据轮换及重定向保护的离线回归；请求轨迹不含密钥，故障后本轮不再重复请求，取消海外引擎选择和 SearXNG 自动回退。按用户要求删除 OpenWebSearch daemon、客户端、SearXNG、WebFetchTool、远程 PDF 和 SAFE 专用链路及对应测试；入口不再管理后台服务，保留注册表、相关性审查与 DeepSeek 官方域重试。注册表元数据不再直接短路搜索，已知标题仍检索引用摘录；同步修改主／专家工具注册、附件 URL 提示及证据边界，运行时无需 Node.js。验证：`src/.venv/bin/python -B -m pytest -q src/tests` 完整回归 148 项通过；相关 Ruff 检查、`git diff --check` 和 `python -m src.main --help` 均通过。真实 API 验证因当前环境未设置密钥而未执行；两项状态均维持“部分实现”。

### 2026-09-13

- `BASE-01`：对 open-webSearch 做逐引擎真实对照：无代理 Bing 对“外籍个人/外商投资企业/股息红利”返回整页抖音，Startpage 超时；本机 HTTP 代理下 DuckDuckGo 首屏直接返回财政部公告2026年第27号、税务总局报道及地方税务原文。启动器现将标准 `HTTPS_PROXY`/`HTTP_PROXY` 显式转换为 open-webSearch 的 `USE_PROXY`/`PROXY_URL`（支持显式退出），CN 默认改为 DuckDuckGo 优先、Bing 备份，补充 `mof.gov.cn` 官方域；发现既有 daemon 的代理状态不一致时拒绝静默复用。非官方幸存结果质量由 `usable` 降为 `leads_only`，防止 Agent 把二手文章当可用证据。新增 supervisor、法域和质量语义测试；状态保持“部分实现”，商业 API 兜底尚未接入。
- `BASE-01`：修复代理设置变更后旧 open-webSearch 进程成为 PPID 1 孤儿、下次启动被一致性保护阻断的问题。`src/websearch/supervisor.py` 为项目自启 daemon 保存 PID、父进程、可执行文件、host/port 身份，仅在父进程已死且命令完全匹配时自动重启；活跃实例和未知进程绝不终止。`src/tests/test_open_websearch.py` 覆盖记录清理、安全接管和活跃 owner 保护。真实启动状态确认 `useProxy: true`，精确标题复测返回上海、四川、北京税务局 3 条官方结果，Bing 301 仅记录为部分失败。
- `BASE-01`、`BASE-06`：根据问题 1 的真实 WebUI 运行日志修复两类失控。搜索边界现会把未加书名号、但形态完整的法规标题自动转换为双引号精确查询；统一模型边界会校验 Nous/native 工具调用，并在上游丢失原始文本前恢复常见的缺引号、换行和尾逗号格式，只修复可无歧义恢复的工具名和 JSON 对象参数，其余调用不执行并自动要求模型重试一次。同时按重复句段频次识别任意周期的规划循环，一旦命中立即关闭流并触发一次干净重试，防止规划文本从数百 tokens 膨胀至万级。新增 `src/tests/test_search_strategy.py`、`src/tests/test_tool_call_compat.py` 与 `src/tests/test_robust_nous.py` 回归覆盖；第二轮真实本地模型复测已确认原始工具调用修复有效，重复生成检测按新日志继续加固，状态保持不变，等待最终回答级 smoke 验收。
- `BASE-01`：针对 CLI 长自然语言查询持续召回词形垃圾的问题，`WebSearchTool` 明确要求已知文件标题使用双引号精确查询，并在工具边界自动把 `《文件全称》` 提取为精确标题加文号；新增运行内近义查询熔断。官方域重试改为优先使用来源注册表推断的主管机关，原始 `*.gov.cn` 结果只有达到主题相关性下限才可提供候选域，避免税务查询被 `dxs.moe.gov.cn` 劫持；CN 税务来源补充中文别名。新增对应搜索策略回归测试，状态保持“部分实现”，等待真实模型 smoke 验证。
- `BASE-06`：重构 WebUI 的视觉布局。桌面端使用 1880px 宽幅容器、固定窄侧栏与弹性主对话区，主对话增加独立卡片层级、轻量强调线和输入框焦点；侧栏统一卡片、间距、阴影与头像尺度，并在 1020px/760px 断点下分别重排右栏和移动端内容顺序。新增 `src/tests/test_webui_display.py` 布局契约测试，状态保持“已完成”。
- `BASE-06`：移除主对话区底部独立的 Gradio 语音录制栏，以空 `gr.State` 继续满足上游消息回调参数契约；文字输入、附件上传与会话保存路径保持不变，并补充 WebUI 源码契约测试。

### 2026-09-12

- `CAP-01`：`DelegatePolicyTask` 描述中直接列出合法 capability 名称。此前两轮真实模型运行中模型先猜测过时名称（如 `tax-policy-analyst`）再靠 `unknown_capability` 错误恢复（A01×7、B02×6、D03×5 次浪费轮次），D01 甚至因此委派失败。机制不变，降低误用率。
- `BASE-01`：搜索审查改为**全量 LLM judge**——不再有初审阈值过滤，judge 审查全部去重后的候选（启发式评分仅作为 judge 不可用时的兜底）；官方域自适应重试的触发条件保留一个最低相关性底线，避免低质量官方命中抑制重试。第三轮实测发现"初审全灭时 judge 无候选可审"的盲区（D01），本次改动即针对该盲区。同时应实测中 bing 限流问题，baidu/sogou 恢复为备用引擎（运行内失败降级机制负责跳过）。全套 140 项测试通过，待第四轮 smoke 验证。
- `BASE-01`：搜索结果过滤升级为两阶段——启发式评分（快车道/阈值过滤）之后，新增 LLM-as-a-judge 二审：judge 为 `FunctionalSubAgent` 子类（`src/agent/functional.py` 新拆出的基类 + `src/agent/judge.py`），输入为主 agent 当前完整上下文（经悬空 tool_calls 清洗）加候选结果，输出结构化 JSON 判定；工具内部直接过滤，主 agent 只看到二审通过的结果和 `discarded_by_judge` 反馈；judge 复用本次运行生效的模型配置（`config/llm.get_active_llm_config`），故障或不可用时回退到启发式结果；搜索预算规则不变。新增 `src/tests/test_search_judge.py` 与 `conftest.py`（隔离模块级配置泄漏），全套 140 项测试通过。尚未经真实模型运行验证，待下一轮 CLI smoke。
- `BASE-06`：修复 terminal 工具结果中断后，带悬空 `tool_calls` 的 assistant 消息被 WebUI/CLI 持久化进会话历史、下一轮请求被 DeepSeek 严格校验拒绝（HTTP 400）的问题；根因是 `FnCallAgent` 每完成一个工具就追加响应，并行调用轮被打断时未完成的调用排在已完成响应**之前**而非尾部，新增 `drop_unresolved_tool_calls` 按调用组配对清洗，并通过 `sanitize_response_tail` 在主 agent 与子代理收尾路径统一使用；同时折叠 WebUI 重试产生的重复 user 消息。新增回归测试于 `src/tests/test_strict_oai.py`，修复后第二轮 15 个 CLI 用例零 400。

- `CAP-01`：移除政策问题模式检测和固定七步流水线，所有请求统一由 normal 模式主 agent 自适应处理；新增 `DelegatePolicyTask` 作为可选、可重复但不自动串联的专家能力，并写入按次能力选择轨迹；新增编排回归测试。机制实现完成，但真实模型 smoke eval 尚未执行，状态由“未开始”更新为“部分实现”。
- `BASE-01`：实现通用搜索相关性评分、来源注册表精确匹配、官方域自适应重试和运行内失败引擎降级；新增 `src/tests/test_search_strategy.py`。完整测试集 132 项通过。状态记为“部分实现”，原因是尚未纳入 42 题 eval，也未完成真实来源的端到端基准。
- 建立本文档，并将 42 道测试题映射为 CAP-01 至 CAP-11。

### 2026-10-07：小池产品与公开答复重构

- 先提交 `6852551` 保存 DeepSeek 原生搜索替换与旧 daemon/tool 删除，再进行本轮产品改造。
- `BASE-04`、`BASE-06`、`XIAOCHI-01`、`XIAOCHI-03`：删除 Gradio 界面及原展示测试，新增独立前端、FastAPI、串行服务和公开答复边界，保留内部上下文、附件及政策链接；Web/CLI 只展示完成后的最终答复，统一追加 AI 提示。旧历史也经过投影；工具、思考、附件正文和配置异常详情不公开。缺少模型密钥时返回可操作的通用配置提示。
- `BASE-01`、`CAP-02`、`XIAOCHI-02`：默认聊天改为 DeepSeek，搜索法域默认 CN，增加税务部门角色、业务配置与税务报告契约。产品身份契约检查通过；无真实密钥，未完成真实联网和税务答复质量评测，相关状态保持部分实现。
- 验证：`src/.venv/bin/python -B -m pytest -q src/tests`（155 项通过）；新接口与答复边界的 scoped Ruff 检查通过。浏览器完成 1280×900 桌面、390×844 手机布局与历史菜单检查；模拟 3 秒 Agent 运行期间只显示等待提示，结束后一次展示带政策链接及 AI 提示的最终答复，刷新恢复同样内容。截图存于 `src/workspace/preview/`。参考站未成功加载，界面及话术依据需求独立实现。

### 2026-10-07：私有 .env 与首轮真实模型迭代

- `XIAOCHI-04`、`BASE-06`：在本地创建权限 0600 的 `.env`，Git ignore 生效且文件未被跟踪；新增 `config/env.py` 和显式 python-dotenv 依赖，聊天/搜索共用并保留环境优先级。`src/tests/test_env.py` 验证仓库路径、共享读取、优先级及缺失文件；没有向代码、报告或日志写入密钥。
- `BASE-01`、`XIAOCHI-02`、`CAP-02`：真实 Chat Completions 和 Messages 原生搜索请求均成功。搜索返回结构化官方链接但无引用摘录，保持内容证据边界，并修复 URL-only 被标记 strong 的误导；新增 `official_excerpt_results`，明确仅链接时停止重复搜标题。初轮六个场景发现首轮澄清冗长和链接定位重复，改为最多三项关键事实、最多三个相关官方链接、业务语言说明缺口，并注入北京时间的当前日期。
- `CAP-01` 评测基础：新增可复现的 `src/evals/xiaochi_smoke.py`，六个真实合成行为场景全部通过（身份、给定参数计算、多轮改写、澄清、附件、官方定位），报告为 `src/workspace/eval/xiaochi-smoke.json`；搜索场景从 22.73 秒及两次搜索改进为 9.63 秒及一次搜索。样本不代表实质税法质量或完整 42 题验收，各相关能力仍保持部分实现。
- 验证：离线回归 158 项通过；改动涉及的新模块与搜索边界 Ruff 通过。真实浏览器完成 .env 生效后的最终计算答复测试，只显示等待提示与最终答复，截图 `src/workspace/preview/xiaochi-live.jpg`。服务已重启，本地预览可直接使用。


### 2026-10-07：中文加粗与首轮响应优化

- `BASE-06`、`XIAOCHI-01`：针对浏览器反馈的 `**中文：**①` 原样显示问题，新增 `src/web/markdown.py` 扩展 Markdown 分隔符规则，保持代码、转义与 HTML 禁用；`src/web/app.py` 对新答复和历史统一使用该渲染器。`src/tests/test_markdown.py` 和 `src/tests/test_xiaochi_web.py` 覆盖中文标点、嵌套链接、代码/转义、恶意 HTML 与历史恢复；浏览器确认原段落为 `strong`、字重 700，截图 `src/workspace/preview/xiaochi-bold-fixed.jpg`。
- `CAP-01`、`CAP-02`、`XIAOCHI-02`：原购房问句运行约 55 秒、三次搜索，涉及未问的出租和持有税等议题。`src/prompts/prompts.py`、`src/config/xiaochi.yaml` 改为缺少主体/地区/资金条件时最多三项澄清，普通咨询约 300 字，不延伸未问事项。真实同问首轮 3.38 秒且无工具调用；答复深度不同，不能据此宣称完整分析同等加速，相关验收状态仍为部分实现。
- `BASE-01`：`src/config/websearch.py`、`src/websearch/deepseek.py` 为原生搜索增加 `DEEPSEEK_SEARCH_EFFORT=low`；`src/agent/judge.py` 仅调整官方 DeepSeek 相关性判断的推理强度，不修改主回答配置。`src/tests/test_deepseek_search.py` 验证请求参数与覆盖设置，`src/tests/test_search_judge.py` 验证主配置不被修改。真实官方链接定位一次搜索、11.33 秒，保持原文缺失说明；单次数据尚不能证明检索本身提速。
- 验证：170 项离线回归通过，七个真实模型合成行为场景 7/7 通过，报告 `src/workspace/eval/xiaochi-smoke.json`；改动文件 Ruff 通过（既有 judge 的异常类型规则不纳入本轮修改）。中英文 README 与运行指南同步更新。预览服务已重启，历史原文保存不变，重新加载后即可看到正确加粗。


### 2026-10-07：小弛命名、书名号加粗与实际进度

- `XIAOCHI-01`、`XIAOCHI-02`、`XIAOCHI-03`、`BASE-06`：将用户名称从“小池”更正为“小弛”，统一配置、角色、CLI、网页、头像和 favicon；兼容旧主 Agent 名称的历史投影。`src/web/markdown.py` 补齐中文与书名号/引号间的加粗开头规则，保持结尾、代码和转义处理。`src/tests/test_markdown.py` 与 `src/tests/test_xiaochi_web.py` 覆盖新旧答复渲染；浏览器确认用户原政策段落为 strong、字重 700，截图 `src/workspace/preview/xiaochi-title-bold-fixed.jpg`。
- `XIAOCHI-03`、`BASE-04`：新增 `src/agent/progress.py` 的请求上下文通知和 `src/web/progress.py` 的有界内存快照；`src/web/service.py`、`src/web/app.py`、`src/web/static/app.js` 按 UUID 发布并每秒查询实际阶段，显示等待秒数，完成/失败后停止轮询。公开字段只有阶段、状态、固定话术与耗时；不包含模型思考、搜索词、文件路径或专家输出。`src/tests/test_progress.py`、`src/tests/test_xiaochi_web.py` 验证运行中可读、阶段白名单、上下文隔离、对话隔离、失败收尾与容量上限；浏览器真实检索显示“小弛正在检索官方政策……”，截图 `src/workspace/preview/xiaochi-progress.jpg`，完成后显示最终答复并恢复输入。
- `BASE-01`、`CAP-01`、`CAP-02`：用户政策问句原记录从 15:49:43 至 15:52:42，约179秒，主代理八次搜索后委派专家。新增 `src/websearch/budget.py` 与 `config/xiaochi.yaml` 三次共享请求预算，覆盖主代理、同步专家及官方域重试。`src/agent/tool_loop_guard.py` 在相关官方候选仅有链接时结束检索，禁用工具生成简短缺口答复；保留完成的工具结果及匹配原生调用 ID，避免后续上下文丢失或 HTTP 400。`src/agent/main_agent.py`、`src/agent/subagent.py` 共用保留规则，`src/tests/test_web_search_integration.py` 覆盖来源保留、多工具 ID 与未执行调用清理，`src/tests/test_deepseek_search.py` 验证整轮预算跨客户端生效、下轮复位。
- `CAP-02`、`XIAOCHI-02`：首轮澄清只含一句说明及至多三项问题、180字内；未取得正文的来源定位限制为三个链接及待核实项，正文350字内（URL不计），不根据标题断言执行日期或法律效果。首次真实迭代发现澄清超长和模型依标题作结论，收紧系统提示并增加运行时检索停止；修复后八个真实合成场景 8/8 通过，用户原政策问句16.22秒、一次搜索，阶段记录包含分析/检索/来源核对/整理；官方定位9.89秒。报告 `src/workspace/eval/xiaochi-smoke.json`。这些是范围和证据边界改进，不等同于实质税法质量验收，相关部分实现状态不变。
- 验证：180 项离线回归通过；新模块、Web 边界、搜索与主 Agent 改动 Ruff 通过，旧专家模块的既有 star-import 问题未纳入本轮范围；文档和架构说明同步。预览服务已重启，原历史正文保存不变，重新载入可看到名称与加粗修复。

### 2026-10-07：恢复自主研究并补齐官方正文

- `CAP-01`、`BASE-01`：按用户“保持原来的 agent 逻辑”要求，移除新增的三次共享网络预算、`websearch/budget.py` 及仅有链接时强制终止逻辑；主 Agent 和专家恢复原研究与收尾路径。阶段通知继续只观察实际执行，不改变工具选择。原有每 Agent 15 次搜索保护和重复查询检查保留，效率改进集中在正文缓存、并行读取及足够证据后的自主停止。
- `BASE-02`、`CAP-04`：新增 `src/websearch/sources.py`，在 `WebSearchTool` 内自动读取 DeepSeek 发现的相关官方 HTML 页面；每批三个页面，失败换其他候选，返回正文、最终 URL、时间、哈希、截断和失败原因；15 分钟有界内存缓存，网页请求无 API 凭据。`src/tests/test_official_sources.py` 覆盖实际财政部/税务页面形态、编码、缓存、403 回退、域名/跳转边界、大小和缺正文。未恢复旧 daemon、WebFetchTool 或远程 PDF；CAP-04 由未开始更新为部分实现，持久快照、分块及定向回读仍缺失。
- `CAP-02`、`XIAOCHI-02`：纠正上一轮将简短原文缺口视为成功的验收；16.22 秒拒答没有完成用户任务，不能作为提速成果。`src/prompts/prompts.py` 与业务配置明确正确性、完整性优先，正文失败先尝试其他官方来源；`src/evals/xiaochi_smoke.py` 改为断言实际官方正文、正式文件、文号、执行日期、适用对象、20%税率及旧条款废止。
- 验证：194 项离线回归通过；八个真实场景 8/8 通过，政策问句取得财政部/地方税务正文并正确回答，用时55.24秒、四次搜索工具调用，真实阶段包含检索、核对来源、读取材料和整理答复。浏览器复测同问成功，中文加粗标签均为 strong、字重700，小弛名称与统一提示正确，截图 `src/workspace/preview/xiaochi-policy-corrected.jpg`。相关 Ruff 与 diff 检查通过；README、运行指南和架构同步。以上证据覆盖一项政策回归，广泛政策质量及42题验收仍未完成，相关状态保留部分实现。

### 2026-10-07：历史对话删除与撤销

- `BASE-04`、`XIAOCHI-01`：`src/agent/conversations.py` 添加可恢复删除与恢复，记录移入 `.trash/`，附件及运行日志保留；`src/web/app.py` 提供删除/恢复接口，`src/web/service.py` 与 Agent 执行共用锁，运行中返回409，避免答复重新写回被删历史。BASE-04 保持部分实现，XIAOCHI-01 保持已完成。
- `src/web/static/app.js`、`index.html`、`style.css`：历史条目右侧删除按钮、确认弹窗及撤销提示；键盘聚焦/桌面悬停可见，触屏直接显示。删除当前记录回到新对话，删除其他记录保留当前答复、草稿及附件选择，侧栏计数和记忆 ID 同步更新。
- 验证：`src/tests/test_conversations.py`、`src/tests/test_xiaochi_web.py` 新增五项回归，覆盖重启、删除/恢复、私有上下文与附件保留、对话隔离、重复/非法请求、跨域及运行互斥；完整199项回归通过。浏览器仅用临时测试记录验证取消、删除其他对话不丢草稿、撤销、删除当前对话与刷新后不复现；桌面和手机布局检查通过。截图 `src/workspace/preview/xiaochi-history-delete.jpg`，相关 Ruff 与 diff 检查通过，README 与运行指南同步。

### 2026-10-07：发送清空与计时文案

- `XIAOCHI-01`、`XIAOCHI-03`：`src/web/static/app.js` 将计时改为“已深度思考 xx 秒”，起始即显示0秒，仍使用原本处理耗时与实际阶段。有效提交同步清空输入框并重置高度；请求失败恢复原草稿（包括空白、换行）和高度，已成功发送但后续刷新失败则不恢复，避免重复提交。两项状态保持已完成，不改 Agent 逻辑。
- 验证：`node --check src/web/static/app.js`、`git diff --check` 通过；用不调用模型、隔离会话的临时浏览器预览验证提交中的输入为空、用户消息保留、计时新文案、成功后为空及失败恢复精确原文。截图 `src/workspace/preview/xiaochi-composer-cleared.jpg`。临时预览关闭，正式页面刷新加载静态改动。

### 2026-10-07：政务蓝主题

- `XIAOCHI-01`、`BASE-06`：`src/web/static/style.css` 统一深蓝主色、蓝灰正文、浅蓝侧栏/选中状态/用户消息与红色强调，移除原绿色及杂色图标配色；新建/发送采用深蓝，删除采用红色，悬停与聚焦同步。`index.html` 浏览器主题色、`favicon.svg` 同步为 `#164b87`，保留现有交互，相关状态维持已完成。
- 验证：浏览器检查桌面首页、聊天正文/政策链接、历史选中、删除弹窗、390×844 手机首页与侧栏，页面无水平溢出；主题变量无缺失。正文、辅助文字、蓝色主按钮、红色删除按钮的配色对比度均超过4.5；`git diff --check` 通过。截图 `src/workspace/preview/xiaochi-government-blue.jpg` 与 `xiaochi-government-blue-mobile.jpg`，临时视口已恢复。README与架构同步。

### 2026-10-07：移除历史标题圆圈

- `XIAOCHI-01`：删除 `src/web/static/style.css` 的 `.history-item:before` 圆圈装饰，保留标题、选中状态及独立删除按钮，状态保持已完成。
- 验证：浏览器全部三个现有历史条目的伪元素内容均为 `none`，标题与删除按钮正常；截图 `src/workspace/preview/xiaochi-history-no-circles.jpg`，`git diff --check` 通过。

### 2026-10-07：移除顶部栏

- `XIAOCHI-01`：`src/web/static/index.html` 删除顶部工作台/对话标题和智能辅助标记；`style.css` 删除对应样式及占位，桌面聊天区域从顶部开始。手机保留独立历史按钮，滚动区域避开按钮；`app.js` 删除标题节点引用和多余请求，同步菜单展开状态。状态保持已完成。
- 验证：`node --check src/web/static/app.js`、`git diff --check` 通过；浏览器确认桌面无 header、工作区顶部为0，历史切换与新建正常；390×844 手机菜单展开、选择后收起和历史恢复正常，无水平溢出，滚动正文区域与按钮不重叠。截图 `src/workspace/preview/xiaochi-no-topbar.jpg`、`xiaochi-no-topbar-mobile.jpg`。临时视口恢复，未改 Agent 逻辑。

### 2026-10-07：拆分提交与 PR 发布前检查

- 汇总现有重构为共享环境/税务配置、官方正文检索、独立聊天与历史管理、文档/评测四个提交；此前的原生搜索迁移提交一并保留。相关能力状态不因发布而升级。
- 验证：完整离线回归再次 199 项通过；前端 JavaScript 语法、diff 检查及新增/改动核心模块的定向 Ruff 检查通过。`config/llm.py` 只检查并修正导入格式，既有旧类型注解和异常类型规则未扩展处理；正文解析器补齐 ClassVar 与正则标志写法。`.env`、workspace 未跟踪且被忽略，候选提交文件未发现真实密钥或私钥。架构说明将评测场景数同步为实际八项；真实模型报告沿用本轮此前已取得的结果，发布检查未重复消耗模型 API。

### 2026-10-08：简朴政务界面与相关问题

- `XIAOCHI-01`、`XIAOCHI-03`、`XIAOCHI-05`：重写前端样式与首页文案，白灰为底、深蓝为操作色，去除装饰头像、宣传语、渐变、阴影、大圆角，保留明确的“发送”文字按钮和既有交互。汇小二参考页本轮未能加载，按用户指定的严肃、低调、简朴方向实现。
- Web 主 Agent 仅增加最终输出的推荐协议，研究循环不变。三个推荐与本轮答案一起生成，提取为独立字段；格式异常、截断或旧历史按类型补足。推荐按钮填入输入框，不自动发送，复制答复不包含推荐。README、运行指南和架构同步。
- 验证：211 项离线回归通过；相关 Ruff、JavaScript 语法和 diff 检查通过。真实 DeepSeek 算术与虚拟材料两项均取得模型生成的三个推荐，保存于 `src/workspace/eval/office-followups-2026-10-08.json`；浏览器验证三项显示、点击填入、刷新一致、历史恢复，桌面与390×844手机无横向溢出，菜单不覆盖正文。截图 `src/workspace/preview/xiaochi-office-home.jpg`、`xiaochi-office-answer.jpg`、`xiaochi-office-mobile.jpg`。本轮仅验证呈现和推荐，未重新验收广泛税务政策质量。

### 2026-10-08：依据汇小二截图细化蓝白界面

- `XIAOCHI-01`：根据用户提供的参考截图重排蓝白内容分区，保留历史侧栏及无顶部通栏布局；白色欢迎/答复卡片配细边框、小圆角和轻微阴影，输入框、发送按钮与三个推荐问题统一样式。新增官方政策资料外链和三条可填入草稿的提问示例；不添加登录、语音或其他未实现入口，不改变模型回答流程。
- `src/web/static/index.html`、`style.css`、`app.js`、`favicon.svg` 为实现文件；国家税务总局、财政部和税收政策法规库入口已按官方页面核对。README 与架构同步。状态保持已完成。
- 验证：桌面1280×720、平板1024×768、手机390×844浏览器检查无横向溢出；欢迎卡片和输入区不重叠，窄屏隐藏右侧栏，菜单与正文分离；历史答复及三个相关问题可恢复，提问示例/推荐点击填入正确草稿。`node --check`、`git diff --check` 通过。截图 `src/workspace/preview/xiaochi-refined-home.jpg`、`xiaochi-refined-answer.jpg`、`xiaochi-refined-mobile.jpg`。本轮为界面修改，不重复模型政策评测。

### 2026-10-08：补齐品牌与政策入口图标

- `XIAOCHI-01` 状态保持已完成，最后更新为2026-10-08。`src/web/static/index.html`、`style.css` 复用小弛 favicon 作为侧栏品牌标识；国家税务总局与财政部入口使用各自官网原始页头资源中的国徽，政策法规库使用自绘书册功能图标。资源保存在 `src/web/static/icons/`，同目录 README 记录来源与用途；不依赖远程热链，不修改 Agent 流程。
- 验证：浏览器确认四个图标全部加载、官方入口名称与链接保留；1280×720 桌面与390×844手机侧栏无横向溢出，品牌名称不挤压，菜单展开/收起正常。截图 `src/workspace/preview/xiaochi-logos.jpg`、`xiaochi-logos-mobile.jpg`；`git diff --check` 通过。本轮仅静态界面修改，未重复模型评测。

### 2026-10-11：界面与相关问题发布检查

- 汇总蓝白政务界面、官方入口图标及每轮三个相关问题推荐，已有能力状态不因发布升级；沿用2026-10-08桌面/手机浏览器和真实推荐验证证据。
- 发布前完整离线回归211项通过；核心改动定向 Ruff、前端 JavaScript 语法、`git diff --check` 通过。确认 `.env` 与 workspace 被忽略且未跟踪；不重复调用模型或扩大政策准确性结论。

### 2026-10-07: on-demand voice input and playback

- `BASE-06`: added a separate Gradio ASR/TTS panel, editable transcripts before sending, configurable Fish voice, and a loopback-only service reusing the installed SenseVoice runtime. Files: `src/voice/`, `src/agent/webui.py`, `scripts/start-asr.sh`. Live ASR and Fish synthesis succeeded, and real Gradio component/event construction passed. Continuous listening, automatic submission and interruption are excluded. Human microphone and full research-flow validation remain pending; see `src/docs/voice.md`.

- `BASE-06`: switched the default Fish voice to 沉稳讲解男声 (`e8370698972f418f9a53644786e90c75`). Started the actual WebUI on port 7860; browser synthesis produced 8.91 seconds of audio and playback advanced. Uploaded audio recognition and insertion into the composer succeeded. Local LLM service remains unavailable; no end-to-end research response was evaluated. Evidence: `src/voice/config.py`, `src/docs/voice.md`. Existing status unchanged.

- `BASE-06` (2026-10-07): enabled DeepSeek as the default provider using `deepseek-flash`, verified against the authenticated models endpoint. Added `scripts/start-web.sh` to load the backend API key from environment or an ignored local file. Restarted the WebUI on port 7860 and verified a real greeting response through the browser. Evidence: `src/config/llm.yaml`, `scripts/start-web.sh`, run `20261007-144118`; no search-heavy evaluation was performed. Existing capability status unchanged.

- `BASE-06` (2026-10-07): replaced the separate voice panel with a composer microphone icon and a speech action beside each main-agent reply. Recording completion inserts editable ASR text; selected replies synthesize through Fish and use a compact pause/replay player. Files: `src/agent/webui.py`, `src/agent/assets/voice_controls.js`, `webui_theme.css`, `src/voice/ui.py`. Real browser synthesis succeeded; physical microphone recording remains pending. Existing status unchanged.

- `BASE-06` (2026-10-07): changed speech to short-segment streaming with synthesis overlapping playback, and switched Fish to 政策解读女声 (`0d6320cfd92647df829a687a7b586f8a`). Speech resolves the selected turn from backend history and reads only its final answer (the explicit conclusion section when present). Intermediate message controls are hidden. Evidence: `src/voice/client.py`, `ui.py`, `src/agent/assets/voice_controls.js`, actual browser multi-segment playback and conclusion-selection check. Existing status unchanged.

- `BASE-06` (2026-10-07): added model-based spoken-conclusion preparation before Fish (`src/voice/narration.py`, `ui.py`). Keeps the full final answer as source, removes research/formatting artifacts, preserves qualifications, caches inspectable narration for 24 hours, and refuses raw-text fallback on failure. Existing streaming playback remains. Validation: actual recent answer normalized in 3.37 seconds (cache hit 0.001 seconds); a real formatter-to-Fish callback produced audio while retaining the 20-working-day condition, exclusion of correction time, and non-guarantee of approval. Injected formatting failure produced no Fish call. Capability status unchanged; model rewriting remains subject to semantic review.

- `BASE-06` (2026-10-07): added post-answer first-sentence prewarming (`src/voice/prepared.py`, `src/agent/webui.py`). Preparation is shared with early playback clicks, keyed by source and voice/model, and never synthesizes the remainder before a playback request. `client.py` keeps the first sentence separate; `ui.py` yields cached first audio before synthesizing the rest. Existing status unchanged.

  Validation: real model/Fish callback observed exactly one TTS call during prewarm (2.8 seconds); playback retrieved the first audio immediately without another TTS call, and only then made the second call. Running Gradio config confirms the background callback is chained after composer unlock.

### 2026-10-11: merge native WebUI and voice integration

- `BASE-06`：合并 `origin/main` 的小弛原生 FastAPI 页面、DeepSeek 搜索、历史恢复与追问；将本分支 Gradio 语音入口迁移到 `src/web/voice.py` 和 `src/web/static/voice.js`，保留 ASR、政策解读女声、模型口播整理、回答完成后只预生成首句、点击后边播边生成。旧 Gradio 页面与依赖按 main 移除，历史实现保留在合并前提交中。
- 验证：Web/API、最终回答边界、追问、模型配置及语音接口的定向检查；语音只读取公开最终回答，不暴露中间 Agent 历史。新增 soundfile 与显式 tqdm 依赖，刷新 src/uv.lock。状态保持不变。

  合并实测：42 项定向检查通过；原生 `/api/voice/asr` 将示例 WAV 转写为“好的，你说。”；浏览器音频播放时间正常推进，显示“政策解读女声 · 1/3”，未观察到播放错误。

### 2026-10-12：修复朗读页面 AI 参考提示

- `BASE-06`、`XIAOCHI-03` 保持已完成，最后更新为2026-10-12。复现统一提示进入最终答复、口播输出和缓存的问题：新增五项回归在修复前全部失败。`src/voice/text.py` 仅剥离末尾的固定产品提示及大小写/人工智能变体；`client.py` 在读取答复和分段前过滤，`narration.py` 在模型输入、输出及缓存读取时过滤。口播提示词更新同步改变准备/口播缓存标识，避免复用旧音频准备结果。页面提示与业务条件、例外和不确定性保留，语音说明同步。
- 验证：`src/tests/test_voice_narration.py` 七项回归涵盖提示变体、重复尾注、模型重新生成提示、缓存残留、业务限制与引用提示文字保留、真实接口准备/分段/公开HTML隔离；完整220项测试通过，改动模块定向Ruff及diff检查通过。真实DeepSeek整理及Fish合成使用一条无个人信息测试文本，口播不含AI提示且生成有效WAV；证据 `src/workspace/eval/voice-footer-2026-10-12.json`、`.wav`。本机8000端口服务已重启加载修复，未删除用户历史或缓存文件。

### 2026-10-12：删除提示自动收起

- `XIAOCHI-01` 保持已完成，最后更新为2026-10-12。`src/web/static/app.js` 将“已删除对话 · 撤销”改为8秒后自动收起；后续删除重置计时，切换/新建对话或有效发送时立即清理。点击撤销暂停计时，恢复失败重新给出8秒操作窗口，恢复成功后隐藏，即使后续列表刷新失败也不再次显示撤销。后端可恢复删除与用户记录保留策略不变。
- 验证：真实浏览器使用新建临时记录确认提示立即出现、超时隐藏、撤销恢复成功并隐藏、新建立即隐藏；测试记录已移入可恢复删除区，原四条历史保留。`node --check src/web/static/app.js` 与 `git diff --check` 通过；截图 `src/workspace/preview/xiaochi-delete-notice-timeout.jpg`。本轮仅前端状态修复，不重复模型调用。

### 2026-10-12：蓝红配色与适度动效

- `XIAOCHI-01` 保持已完成，最后更新为2026-10-12。`src/web/static/style.css` 调整深蓝侧栏、浅蓝工作区与红色入口/标题强调，增加柔和渐变与悬停层次；`index.html` 使用代码 SVG 资料图形，`app.js` 为四个业务入口增加装饰图标。增加短入场、按钮轻微抬起、输入聚焦、答复入场、等待细线与录音反馈；首页虚线环缓慢转动，窄屏隐藏，`prefers-reduced-motion` 禁用所有动画和过渡。动效不更改 Agent 执行或表示完成百分比，中英文 README 与架构说明同步。
- 验证：浏览器1280px桌面、1024px平板、390px手机无横向溢出，首页欢迎卡片/输入区无重叠；手机历史菜单、既有答复恢复、三个推荐、业务入口与推荐点击填入正常；DOM确认四个图标、装饰环/答复动画及减少动态效果规则存在。主要蓝/红入口文字及侧栏文字对比度超过4.5。`node --check`、`git diff --check` 通过。截图 `src/workspace/preview/xiaochi-blue-red-home.jpg`、`xiaochi-blue-red-answer.jpg`、`xiaochi-blue-red-mobile.jpg`；本轮无新模型调用，不重复模型质量评测。

### 2026-10-12：收敛装饰线与政策图标动效

- `XIAOCHI-01` 保持已完成，最后更新为2026-10-12。`src/web/static/index.html` 移除品牌名旁红线节点；`style.css` 移除历史选中项红色 inset 边线、两张右侧卡片顶部蓝/红伪元素，侧栏键盘焦点改为浅蓝。三个政策入口图标容器在悬停和键盘聚焦时轻微抬起、缩放，并进行一次扫光；图标原文件不变，系统减少动态效果时仍停用动画与过渡。
- 验证：浏览器确认品牌线节点为0、选中历史阴影为none、两卡顶部伪元素content均为none；三个入口逐一键盘聚焦均触发icon-sheen，图标transform变化正常，页面无横向溢出。截图 `src/workspace/preview/xiaochi-clean-accents.jpg`；`git diff --check` 通过。纯样式调整，不重复模型调用。

### 2026-10-12：取消首页线条并明确等待状态

- `XIAOCHI-01` 保持已完成，最后更新为2026-10-12。`src/web/static/style.css` 删除欢迎卡片顶部红蓝线及“业务工作台”前的小横线；将不明确的红蓝伸缩线替换为阶段文字左侧的蓝色转圈，耗时排在阶段下方。保留现有真实阶段和计时逻辑、status语义以及减少动态效果设置；架构说明同步。
- 验证：独立8001端口预览使用临时会话及12秒模拟Agent，不调用模型或Fish、不改用户历史；浏览器确认两处首页伪元素content为none、旧等待线为none、新转圈动画为waiting-spin且阶段/耗时仍显示；答复完成后转圈移除，发送按钮恢复可用。截图 `src/workspace/preview/xiaochi-home-no-topline.jpg`、`xiaochi-waiting-spinner.jpg`。`node --check`、`git diff --check` 通过。

### 2026-10-12：Q 版动态品牌形象

- `XIAOCHI-01` 保持已完成，最后更新为2026-10-12。使用内置 imagegen 根据用户人物插画生成透明 Q 版精灵图，保留长发、黑色上衣、项链及暖黄色长裤；生成提示、素材来源和 CSS/Lottie/Rive 方案比较记录在 `src/web/static/mascot/README.md`、`generation-prompt.txt`。`index.html` 替换侧栏字标，`mascot.css` 按实测帧中心/脚底基线校准，提供待机眨眼/轻呼吸、悬停与键盘聚焦三轮挥手、处理中歪头与三点提示；`app.js` 复用 busy 状态并监听页面可见性。减少动态效果时使用静态首帧，页面隐藏/手机侧栏关闭时暂停；无新增运行库，不表示模型思考过程或完成比例。
- 验证：真实 Chromium 浏览器检查四帧眨眼和四帧挥手位置、键盘聚焦、处理中状态、成功和失败后恢复、减少动态效果、隐藏页面及手机侧栏暂停；1280×844、1024×844、390×844 无横向溢出，浏览器无脚本异常。对话接口由浏览器模拟，无真实模型调用或用户历史写入。`src/tests/test_xiaochi_web.py` 17项通过（两项既有依赖弃用警告），`node --check src/web/static/app.js` 与 `git diff --check` 通过。检查记录 `src/workspace/preview/xiaochi-mascot-check.json`；截图 `xiaochi-mascot-desktop.png`、`xiaochi-mascot-busy.png`、`xiaochi-mascot-mobile.png` 位于同目录。

### 2026-10-12：多业务首页、官方入口与输入区调整

- `XIAOCHI-01`、`XIAOCHI-03` 保持已完成，`XIAOCHI-02` 保持部分实现，最后更新均为2026-10-12。`config/xiaochi.yaml` 定义税收、外汇、商务发改三类共十二个问题草稿入口；`web/app.py` 公开类别配置，保留原四个quick_questions；`static/app.js` 切换类别保留草稿，事项点击填入且不自动发送。`index.html`、`style.css` 移除输入框上方“提出问题/可附相关材料”和独立页脚，正文最小高度112px、自动增长上限240px，整体约190px；答复末尾参考提示保留。外汇局和发改委标识从官网获得，原文件本地保存，来源见 `static/icons/README.md`。现有品牌动画保留，核心Agent流程未调整。
- 验证：完整220项回归、Web模块Ruff、JavaScript语法和diff检查通过；浏览器1412×827桌面、1024×768平板、390×844手机无横向溢出、首页/输入区不重叠。五个政策图标加载成功，外汇/商务发改类别切换、草稿保留、事项填入与历史恢复正常；独立页脚与输入标题节点均不存在，历史答复仍含参考提示。截图 `src/workspace/preview/xiaochi-business-home.jpg`、`xiaochi-business-mobile.jpg`。服务已重启加载配置。本轮无新模型调用，不据首页入口扩大业务质量验收结论。

### 2026-10-12：修复挥手帧串图并放大形象

- `XIAOCHI-01` 状态保持已完成，最后更新为2026-10-12。用户截图中的头顶两点来自精灵图上一行鞋底漏入挥手视口。`src/web/static/mascot/mascot.css` 将素材与所有帧坐标统一放大25%，视口由64×76改为80×95；使用顶部3px、底部1px帧间裁切，保留当前人物头发/脚底并移除相邻行内容。`src/web/static/style.css` 同步收窄品牌区间距，适配当前副标题；素材说明同步。
- 验证：逐一查看四个挥手帧截图，头顶残影消失、人物完整；浏览器复验眨眼/挥手、聚焦、忙碌成功与失败恢复、减少动态效果和隐藏暂停。1280/1024/390px页面与品牌区均无横向溢出。记录 `src/workspace/preview/xiaochi-mascot-check.json`、四张 `xiaochi-mascot-wave-*.png` 及桌面/手机截图；`git diff --check` 通过。本轮为CSS裁切与尺寸调整，不调用模型或改动用户对话。

### 2026-10-12：详细部署教程与脱敏环境模板

- `XIAOCHI-04` 保持已完成，最后更新为2026-10-12。新增根目录 `.env.example`，DeepSeek/Fish 凭据留空，并列出声线、搜索、代理及脚本端口的可选配置；`.gitignore` 仅放行模板，私有 `.env`、`.env.*` 和 `.local/` 仍被忽略。没有复制或更改本机真实密钥。
- `README.zh-CN.md` 与 `README.md` 补齐 Git/uv/Python3.12、锁定依赖、API 导入、Web/CLI、Fish 朗读、外部 SenseVoice 环境/模型、Linux systemd/SSH 隧道、Windows、更新备份与故障排查；`src/README.md`、`src/docs/voice.md` 同步交叉链接和端口/ASR 环境边界。单用户共享历史与串行执行范围明确，未据文档升级多人部署或政策质量验收。
- 验证：锁定依赖离线 dry-run 成功；文档内本地链接、代码块与 Bash 语法检查，启动 `--help`、Git ignore 检查和仅输出布尔状态/模型地址的密钥加载检查通过；`src/tests/test_env.py` 与 `src/tests/test_llm_config.py` 共8项通过。未安装额外语音环境、改动运行服务或执行服务器部署；Windows/systemd 示例依据实际入口核对，未在对应系统实机部署。
