# 小弛 Agent

小弛基于 3wagent 的 Agent 核心，面向政府税务部门工作人员，辅助税收政策查询、办税材料解读、咨询答复草拟和税费计算。默认讨论中国内地事项；用户明确提出涉外情境时，再扩展其他法域。

[English](README.md) · [运行与配置](src/README.md) · [架构说明](src/docs/architecture.md) · [能力路线图](src/docs/agent-capability-roadmap.md)

## 主要功能

- 独立聊天界面：历史对话、新建对话、删除与撤销、附件上传、政策链接与答复复制。首页按税收、外汇、商务发改提供三类、十二项业务草稿入口；切换类别保留已写草稿。
- 蓝红工作界面：深蓝历史侧栏、浅蓝咨询区与白色卡片，红色标识业务入口；轻微入场、悬停与等待动画提供反馈，支持系统减少动态效果设置。窄屏保留主要对话区。
- 相关问题：每条答复下方提供三个后续问题，点击填入输入框后可编辑发送，恢复历史时保留。
- 材料处理：支持 PDF、DOCX、表格、CSV 和文本等格式，每条问题最多 5 个附件，单文件最多 25 MB。
- 税务辅助：结论在前，按需补充适用条件和政策依据；信息不足时先询问最多三项关键事实。报告与答复草稿只按明确请求生成。
- 最终答复展示：Web 与 CLI 只显示完成后的答复。思考、工具调用、工具结果与专家中间文本留在后端，历史恢复同样过滤。
- 阶段进度：处理中显示“小弛正在检索官方政策……”等实际阶段及“已深度思考 xx 秒”，不展示思考正文或工具参数。
- 发送体验：提交后立即清空输入框；发送失败时恢复原文与换行，方便重试。

输入框已扩大，移除输入框上方标题及底部重复提示；每条最终答复仍由程序统一追加：

> 以上内容由 AI 生成，仅供参考，具体请以现行有效政策及主管税务机关确认口径为准。

历史条目右侧提供删除按钮（桌面端悬停或键盘聚焦时显示，触屏端直接显示）。确认后移出历史列表，可点击“撤销”恢复。删除当前对话回到新对话，删除其他记录保留当前答复和草稿；生成答复时暂停历史管理。

## 详细部署教程

以下主流程适用于 macOS / Linux，命令从仓库根目录执行；Windows PowerShell 的启动路径见后文。建议使用 Python 3.12，项目要求 Python 3.11 及以上。配置说明核对于 2026-10-12。

### 1. 选择需要启用的功能

| 部署方式 | 需要准备 | 启动进程 |
|---|---|---|
| 文字聊天、附件与联网检索 | DeepSeek API Key | Web |
| 文字功能＋答复朗读 | DeepSeek Key、Fish Key | Web |
| 再加语音输入 | 上述配置、本地 SenseVoice 代码/模型/环境 | Web＋ASR |

默认聊天和联网搜索共用 DeepSeek 密钥。口播稿整理也使用当前聊天模型；Fish 只负责合成声音。语音输入在本机 CPU 上运行，不需要语音识别 API Key。主流程不需要 Node.js、前端编译、Docker、数据库或旧搜索 daemon；使用云端模型时不需要在本机部署大模型。

### 2. 安装工具、拉取代码和依赖

准备 Git、curl 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)。已有这些工具可跳过安装。

macOS 已安装 Homebrew 时：

```bash
brew install git uv
```

Ubuntu / Debian：

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates python3 libsndfile1
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

其他 macOS / Linux 环境也可使用上述 uv 官方安装脚本；系统依赖按发行版安装。核对工具，再获取项目：

```bash
git --version
uv --version
git clone https://github.com/SegemiPL/xiaochi.git xiaochi-agent
cd xiaochi-agent
uv python install 3.12
uv sync --project src --python 3.12 --locked
src/.venv/bin/python --version
```

`--project src` 是必需的：运行依赖在 `src/pyproject.toml`，锁文件是 `src/uv.lock`，Python 环境生成于 `src/.venv/`。`--locked` 使用仓库声明的锁文件，发现依赖声明与锁文件不一致时停止。后续同步时应保留所需的全部 `--extra` 参数，否则可选依赖会被移除。Python 安装方式见 [uv 官方说明](https://docs.astral.sh/uv/guides/install-python/)。不必激活虚拟环境，直接使用它的 Python 即可。

如需运行测试或读取旧版 `.xls` 文件，可选安装：

```bash
uv sync --project src --python 3.12 --locked --extra dev
# 仅需要读取旧版 .xls 时使用：
uv sync --project src --python 3.12 --locked --extra dev --extra legacy-excel
```

### 3. 创建 .env 并导入 API 密钥

从 [DeepSeek 控制台](https://platform.deepseek.com/api_keys) 获取自己的 API Key；需要朗读时，再按 [Fish 官方密钥教程](https://docs.fish.audio/developer-guide/getting-started/api-key) 获取 Fish Key。两家的密钥互不通用。

仓库根目录提供不含真实密钥的 `.env.example`。首次部署复制模板；已有 `.env` 时直接编辑，下面的命令不会覆盖它：

```bash
if [ ! -f .env ]; then cp .env.example .env; fi
chmod 600 .env
nano .env
```

填写以下字段（将说明文字替换为实际值）：

```dotenv
DEEPSEEK_API_KEY=填入你的DeepSeek密钥
FISH_AUDIO_API_KEY=填入你的Fish密钥
```

只使用文字功能时，`FISH_AUDIO_API_KEY` 可留空。`.env` 应与根目录 `README.md` 同级，不要放进 `src/`。Web、CLI 和搜索自动加载这个文件；现有进程环境变量优先，不执行变量插值。修改 `.env` 后重启 Web。`.env`、私有 `.env.*` 和 `.local/` 被 Git 忽略，只有脱敏的 `.env.example` 可提交。

可检查密钥是否加载，下面只输出配置状态，不打印密钥，也不调用外部 API：

```bash
src/.venv/bin/python - <<'PY'
import os
from src.config.env import load_project_env
from src.config.llm import load_llm_config
from src.voice.config import api_key
load_project_env()
print('DeepSeek 已配置：', bool(os.getenv('DEEPSEEK_API_KEY')))
print('Fish 已配置：', bool(api_key()))
config = load_llm_config()
print('聊天模型：', config['model'])
print('聊天地址：', config['model_server'])
PY
```

也支持在当前终端 `export DEEPSEEK_API_KEY=...` 后启动；不建议同时维护多份不同的值，以免旧环境变量覆盖 `.env`。

**密钥文件方式：**Fish 支持 `FISH_AUDIO_API_KEY_FILE=/绝对路径/fish-api-key.txt`，文件仅保存密钥本身。DeepSeek 的文件方式使用 `DEEPSEEK_API_KEY_FILE`，须通过 `scripts/start-web.sh` 导入，直接运行 `python -m src.main` 不读取此文件变量。没有 DeepSeek 环境密钥时，脚本读取指定文件；若未指定，则尝试根目录 `.local/deepseek-api-key.txt`，该文件不存在时再尝试相邻教育项目的同名文件。建议新部署明确配置根目录 `.env`。上面的检查针对 `.env`/进程环境；DeepSeek 文件回退是在启动脚本中发生的。

**聊天与搜索配置：**密钥共用，但模型与端点分开配置。以下默认值来自当前仓库：

| 配置 | 默认值 / 设置方式 |
|---|---|
| 聊天模型 | `src/config/llm.yaml` 的 `deepseek-flash`，或 `--model` 覆盖 |
| 聊天地址 | `src/config/llm.yaml` 的 `https://api.deepseek.com` |
| 联网搜索模型 | `deepseek-v4-flash`，可用 `DEEPSEEK_SEARCH_MODEL` 覆盖 |
| 联网搜索地址 | `https://api.deepseek.com/anthropic/v1`，可用 `DEEPSEEK_SEARCH_BASE_URL` 覆盖 |
| 其他聊天 provider | `--provider kimi` 配合 `MOONSHOT_API_KEY`；`--provider local` 配合已启动的兼容服务 |

`--model` 只覆盖聊天模型。聊天选择其他 provider 时，联网搜索仍需要 DeepSeek Key。聊天地址应在 YAML 配置，不通过 `DEEPSEEK_BASE_URL` 改写；搜索参数与代理变量可写入根目录 `.env`。更多参数见[运行指南](src/README.md#模型与搜索)。

### 4. 启动网页或 CLI

推荐直接启动，默认地址为 [http://127.0.0.1:8000](http://127.0.0.1:8000)：

```bash
src/.venv/bin/python -m src.main
```

看到 `Uvicorn running on http://127.0.0.1:8000` 后打开浏览器。网页会自动读取配置和历史；首条问题才创建聊天模型。没有密钥时可预览界面，但不能正常提问。

可选启动命令：

```bash
# 明确指定地址和端口
src/.venv/bin/python -m src.main --host 127.0.0.1 --port 8000

# 使用启动脚本，保持网页地址为 8000
bash scripts/start-web.sh --port 8000

# 终端模式
src/.venv/bin/python -m src.main --cli

# 覆盖聊天模型名称，不改变独立搜索模型
src/.venv/bin/python -m src.main --model deepseek-flash
```

| 启动方式 | 默认端口 | 覆盖方式 |
|---|---|---|
| `python -m src.main` | 8000 | `--port` |
| `bash scripts/start-web.sh` | 7860 | `--port`，或该脚本读取的 `XIAOCHI_PORT` |
| `bash scripts/start-asr.sh` | 8772 | 本文保持默认 ASR 端口 |

`XIAOCHI_PORT` 不控制直接启动的 `src.main`。前台服务用 `Ctrl+C` 停止；修改环境配置后，停止再运行同一启动命令。

先检查网页接口：

```bash
curl --noproxy '*' http://127.0.0.1:8000/api/config
```

返回包含 `"name":"小弛"` 的 JSON 表示 Web 可访问，此检查不验证上游模型。随后在网页发送“仅按含税金额1130元、税率13%计算不含税金额和税额，不判断税率适用性”，应得到不含税金额1000元、税额130元。这个步骤会调用模型；联网检索另用需要官方依据的问题验证。

### 5. 配置答复朗读（可选）

朗读只需要 Web 与已填写的 Fish Key，**不需要启动 ASR**。当前代码请求 `https://api.fish.audio/v1/tts`，模型固定为 `s2.1-pro-free`，不会在错误时自动切换付费模型；账户权限和额度仍由 Fish 决定。

默认声线是“政策解读女声”。可在 `.env` 中覆盖：

```dotenv
FISH_VOICE_ID=0d6320cfd92647df829a687a7b586f8a
FISH_VOICE_NAME=政策解读女声
```

重启 Web，完成一条回答后点击“朗读结论”。后端先整理口播稿，再分段合成；回答完成后尝试预生成首句，点击后才播放并继续生成后续段落。参考提示只显示、不朗读；文字原文保留。朗读故障不会阻止文字答复。首次准备可能有等待，重放可使用缓存；详细规则见[语音文档](src/docs/voice.md)。

### 6. 准备并启动本地语音输入（可选）

当前 ASR 复用独立 `one2one-education` 项目的 `prototypes/voice/engine.py` 与 SenseVoice ONNX 模型。**本仓库不包含该项目，也不会自动下载其代码。**先由维护者提供匹配的项目版本；至少应包含引擎、`prototypes/voice/requirements.lock` 和 `prototypes/voice/scripts/download_models.py`。没有这个依赖项目时，可先使用文字功能和 Fish 朗读。

在该依赖项目根目录准备环境和模型（替换示例绝对路径）：

```bash
cd /absolute/path/one2one-education
uv venv --python 3.12 .venv-voice
uv pip install --python .venv-voice/bin/python -r prototypes/voice/requirements.lock
.venv-voice/bin/python -m prototypes.voice.scripts.download_models
```

小弛基本转写调用 SenseVoice 的 CPU 识别路径，不需要为它安装教育项目的 GPT-SoVITS、IndexTTS 或本地 TTS 权重。模型位于依赖项目的：

```text
.data/voice-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/
├── model.int8.onnx
└── tokens.txt
```

另开终端，回到小弛根目录启动专用 ASR 服务：

```bash
cd /absolute/path/xiaochi-agent
export VOICE_ASR_REPO=/absolute/path/one2one-education
export VOICE_ASR_PYTHON="$VOICE_ASR_REPO/.venv-voice/bin/python"
bash scripts/start-asr.sh
```

若系统没有 `python3` 命令，可以在设置上述变量后直接使用已准备的解释器：

```bash
"$VOICE_ASR_PYTHON" -m src.voice.asr_service
```

`start-asr.sh` 本身**不自动加载 `.env`**；其路径要通过当前终端的 `export` 或根目录 `.local/voice.json` 提供。若依赖环境名就是 `.venv-voice`，也可在 `.local/voice.json` 合并以下字段，省去每次导出路径：

```json
{
  "asr_repo": "/absolute/path/one2one-education",
  "asr_url": "http://127.0.0.1:8772"
}
```

保留已有声线或密钥文件字段，不要覆盖整份现有配置。ASR 与 Web 在同一主机运行；Web 的识别目标默认是 `http://127.0.0.1:8772`。`VOICE_ASR_URL` 只改变 Web 请求的目标，不会改变 ASR 启动监听端口。

检查模型就绪状态：

```bash
curl --noproxy '*' http://127.0.0.1:8772/api/status
```

应看到 `asr.ready` 为 `true`。然后在小弛页面允许麦克风权限，点击录音，再次点击停止；识别结果填入输入框，由用户核对后发送。录音最多约60秒。浏览器麦克风需要 localhost 或 HTTPS，远程浏览器访问可按下一节使用 SSH 隧道。

### 7. Linux 服务器长期运行与远程访问

当前为单用户、共享本机历史的应用，没有账号/部门权限隔离，同一进程串行运行 Agent，不启用多个 workers。服务器部署可保留 localhost 监听，通过已有 SSH 账号访问。

先按上文在服务器安装代码、依赖和 `.env`。以 systemd 管理 Web，示例使用已存在的 `xiaochi` 账号和 `/opt/xiaochi-agent` 目录；按实际用户和绝对路径修改，保证该用户能读取 `.env` 并写入 `src/workspace/`、`src/reports/`：

```ini
# /etc/systemd/system/xiaochi-web.service
[Unit]
Description=Xiaochi Web
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=xiaochi
WorkingDirectory=/opt/xiaochi-agent
ExecStart=/opt/xiaochi-agent/src/.venv/bin/python -m src.main --host 127.0.0.1 --port 8000
Environment=PYTHONUNBUFFERED=1
UMask=0077
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

保存服务文件后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now xiaochi-web
sudo systemctl status xiaochi-web
journalctl -u xiaochi-web -f
```

Web 会自己读取根目录 `.env`，不需要在服务文件里写真实密钥。修改 `.env` 后：

```bash
sudo systemctl restart xiaochi-web
```

ASR 可用第二个同类服务管理，`WorkingDirectory` 仍是小弛目录，`ExecStart` 改成依赖项目 `.venv-voice/bin/python -m src.voice.asr_service`，并在服务文件设置 `Environment=VOICE_ASR_REPO=/绝对路径/one2one-education`。它不读取 Web 的进程变量，须独立提供路径；默认仍监听8772。

在自己的电脑建立隧道（替换账号和服务器地址）：

```bash
ssh -N -L 8080:127.0.0.1:8000 your-user@your-server
```

保持此终端打开，用浏览器访问 [http://127.0.0.1:8080](http://127.0.0.1:8080)。录音由远程 Web 后端转交同服务器的 ASR，因此只需转发 Web 端口。若已有受控内网部署，可指定 `--host` 或使用提供 HTTPS 的反向代理；该版本仍共享一套历史，不会因此获得多用户隔离。

### 8. Windows PowerShell 基本启动

已安装 Git 后，使用 uv 的 [WinGet 安装方式](https://docs.astral.sh/uv/getting-started/installation/#winget)。在 PowerShell 中：

```powershell
winget install --id=astral-sh.uv -e
# 安装后重新打开 PowerShell
git clone https://github.com/SegemiPL/xiaochi.git xiaochi-agent
cd xiaochi-agent
uv python install 3.12
uv sync --project src --python 3.12 --locked
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
.\src\.venv\Scripts\python.exe -m src.main --port 8000
```

`.env` 字段与上文相同，网页仍是8000。CLI 使用 `--cli`；检查和测试命令中的 `src/.venv/bin/python` 换为 `.\src\.venv\Scripts\python.exe`。仓库 Bash 脚本和 systemd 示例面向 macOS / Linux；Windows 的语音依赖环境需另行准备并验证。

### 9. 更新、备份与常见问题

更新前保存本地改动和会话数据，然后在仓库根目录：

```bash
git status --short
git pull --ff-only
uv sync --project src --python 3.12 --locked
# systemd 部署：
sudo systemctl restart xiaochi-web
```

前台部署按 `Ctrl+C` 后重新启动；修改静态界面后刷新浏览器。持久化数据在 `src/workspace/`，报告在 `src/reports/`，更新时保留这些目录；`.env` 和 `.local/` 按私有配置单独迁移。历史删除是移入 `.trash/`，不会清除附件或运行日志。

| 问题 | 排查方式 |
|---|---|
| 缺包或模块无法导入 | 从仓库根目录运行，使用 `src/.venv/bin/python`；重新执行 `uv sync --project src --locked` |
| `uv` 找不到 | 重开终端，或将 `$HOME/.local/bin` 加入 PATH；核对 `uv --version` |
| `--locked` 报锁文件不一致 | 确认代码和 `src/uv.lock` 来自同一版本；开发者更新依赖时同步提交锁文件 |
| `address already in use` | 已有服务占用端口，停止自己启动的旧服务，或使用 `--port 8002` |
| 页面正常但提示模型未配置 | 根目录 `.env` 的 DeepSeek Key 为空或未加载；修改后重启，检查是否有旧进程变量覆盖 |
| DeepSeek 401 / 402 / 429 | 分别核对密钥、账户余额/权限、限流；参见 [官方错误码](https://api-docs.deepseek.com/quick_start/error_codes/) |
| 聊天可用但搜索报错 | 搜索模型/端点独立配置，检查 `DEEPSEEK_SEARCH_MODEL` 和 API 权限，不会回退旧搜索引擎 |
| Fish 401 / 402 / 403 / 429 | 核对 Fish Key、模型额度、声线权限与限流；确认不是误填 DeepSeek Key |
| Fish 连接失败或超时 | 检查服务器到 `api.fish.audio` 的网络和代理；稍后手动重试 |
| “未找到已有的语音 Python 环境” | 核对 `VOICE_ASR_REPO`、`VOICE_ASR_PYTHON` 与 `.venv-voice`；只填 Fish Key 不能修复 ASR |
| ASR `ready=false` / `MODEL_MISSING` | 在依赖项目运行模型下载脚本，确认上文两个模型文件存在 |
| 麦克风无法录音 | 检查浏览器授权，使用 localhost / HTTPS；远程使用 SSH 隧道或 HTTPS 入口 |
| 使用代理后本机请求失败 | 添加 `NO_PROXY=localhost,127.0.0.1,::1`；只在网络需要时设置代理 |
| 并发请求提示忙碌 | 等待本轮完成；当前单进程串行执行，不通过多个 workers 规避 |

代理和搜索参数、其他聊天 provider 的详细说明见[运行指南](src/README.md)，语音缓存和声线配置见[语音文档](src/docs/voice.md)。

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
uv sync --project src --python 3.12 --locked --extra dev
src/.venv/bin/python -m pytest -q src/tests
```

显式运行真实 DeepSeek 行为测试：

```bash
src/.venv/bin/python -m src.evals.xiaochi_smoke
```

该命令会产生 API 用量，使用独立临时会话，报告写入 `src/workspace/eval/xiaochi-smoke.json`。报告不记录密钥、请求头或完整模型配置。

| 验证项 | 最近验证结果 |
|---|---|
| 离线回归 | 2026-10-12：220 项通过 |
| 真实模型测试 | 8/8 通过：身份、给定参数计算、多轮改写、税额澄清、跨境操作澄清、附件、官方链接定位、近期政策正式文件与适用范围核验 |
| 浏览器联调 | 桌面和移动端布局、等待提示、最终答复与历史恢复已检查；真实计算及中文加粗显示已验证 |

最新实测：购房问题首轮澄清 2.13 秒；官方链接定位 11.16 秒；外籍个人分红政策完整答复 55.24 秒、四次搜索工具调用。此前 16.22 秒的缺口答复没有完成用户任务，不能作为成功提速基准。政策回归现检查实际取得的正文，以及最终答复的文件名称、文号、执行日期、税率、适用对象和旧条款废止。

这八个样本验证产品行为及一项政策回归；完整 42 题和广泛税务政策质量验收仍未完成。各能力状态见[能力路线图](src/docs/agent-capability-roadmap.md)。

## 运行范围与数据

当前为本地单用户版本，默认绑定 `127.0.0.1`，没有账号与部门权限体系。原核心部分状态仍为进程全局变量，因此单个进程串行处理问题；多个 workers 尚不受支持。

对话、上传文件、解析结果与运行日志保存在 Git 忽略的 `src/workspace/`，按请求生成的报告位于 `src/reports/`。完整内部上下文与公开对话分别持久化；HTTP 接口只返回公开消息，静态路由不暴露 workspace 或模型配置。

对话删除采用可恢复的移除方式，记录移到会话目录的 `.trash/`；附件与运行日志保留，不作为彻底清除数据的功能。

2026-10-08：完成简朴政务界面与三个相关问题推荐。真实计算和材料整理两项验证均由同轮模型生成三个问题；元数据不进入正文，历史恢复保持一致。新增推荐验证不替代上述政策质量验收。
