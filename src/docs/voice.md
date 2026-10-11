# 普通语音识别与合成

更新：2026-10-07。实现分支 `codex/asr-fish-tts`。

语音操作融入聊天界面，不再提供独立的语音折叠面板：

1. 点击输入框旁的麦克风图标，允许浏览器使用麦克风，开始录音。
2. 点击“停止”结束录音，自动识别并填入主输入框；已有文字和附件保留。核对后自行发送。
3. 点击某条 AI 回复旁的声音图标，只朗读该轮最终回答；由模型整理为适合直接朗读的结论口播稿。中间工具调用、思考和进度消息不进入 TTS。
4. 结论分成短段，首段返回就开始流式播放，后台同时生成后续段；紧凑播放条支持暂停和重放。最多 12000 字，超长回复会提示。首段仍需等待 Fish 请求，网络慢时后续段也可能产生间隔。

仅按需 ASR/TTS，不包括持续监听、自动提交、RNNoise 实时降噪、语气词检测、打断。原始录音不作为多模态附件发送给研究模型；用户确认后的文字才进入对话。

## 运行

应用沿用 `src/README.md` 中的启动方式。首次安装：

```bash
uv sync --project src
npm ci --prefix src/infra/open-websearch
```

启动页面（默认 DeepSeek `deepseek-flash`）：

```bash
bash scripts/start-web.sh
```

启动脚本优先使用 `DEEPSEEK_API_KEY`，否则读取 `DEEPSEEK_API_KEY_FILE` 指定文件，默认 `.local/deepseek-api-key.txt`；本仓库文件不存在时，复用相邻教育项目的同名 Key 文件。Key 仅放入后端环境。直接运行 `python -m src.main` 时需要自行设置环境变量。

另开终端，在仓库根目录启动仅包含 ASR 的本机服务：

```bash
bash scripts/start-asr.sh
```

监听 `127.0.0.1:8772`，不需要启动 one2one 的页面、TTS 或模型训练服务器。默认复用相邻 `../one2one-education` 仓库的 SenseVoice 代码、已下载模型和 `.venv-voice` 环境；该目录必须保留。可通过 `VOICE_ASR_REPO` 和 `VOICE_ASR_PYTHON` 改变位置。这是当前机器的模型复用方案，不是包含 ASR 权重的独立发布包。

如果已经运行原项目的语音服务，也可设置 `VOICE_ASR_URL=http://127.0.0.1:8769`，直接复用 `/api/asr`，无需另启 8772。ASR URL 仅接受本机 HTTP 地址。

## TTS 与声线配置

TTS 使用从 one2one-education 移植的 Fish 适配器，直接请求官方 `https://api.fish.audio/v1/tts`，模型固定为 `s2.1-pro-free`。默认声线：

- 名称：政策解读女声
- ID：`0d6320cfd92647df829a687a7b586f8a`

Key 读取顺序：`FISH_AUDIO_API_KEY` / `FISH_API_KEY` 环境变量 → `FISH_AUDIO_API_KEY_FILE` 指定文件 → `.local/voice.json` 的 `key_file` → 本仓库 `.local/fish-api-key.txt`。不向浏览器暴露 Key，不自动回退付费档。

后续更换声线，设置：

```bash
export FISH_VOICE_ID='新的 Fish 声线 ID'
export FISH_VOICE_NAME='新的声线名称'
export FISH_AUDIO_API_KEY_FILE="$HOME/code/one2one-education/.local/fish-api-key.txt"
```

也可编辑本机忽略文件 `.local/voice.json`（已为当前机器配置）：

```json
{
  "voice_id": "0d6320cfd92647df829a687a7b586f8a",
  "voice_name": "政策解读女声",
  "key_file": "~/code/one2one-education/.local/fish-api-key.txt",
  "asr_repo": "~/code/one2one-education",
  "asr_url": "http://127.0.0.1:8772"
}
```

配置文件每次请求读取，改后下一次合成即生效；环境变量变化需要重启应用。声线配置与教育项目分开，不会改变对方当前选择。`.env` 不会由本模块自动加载，可在启动前自行导出环境变量。

## 缓存与边界

`src/voice/fish.py` 与 `audio_cache.py` 复用原有实现；短句按参数缓存于 `src/workspace/voice/audio-cache`，容量上限 128 MiB，24 小时空闲过期。键包括声线、模型、文本和语速，换声线不会复用旧声线音频。页面朗读按句切成约 60–120 字的短段，通过 Gradio 流式音频依次播放。服务端每产出一段立即开始下一段；失败会明确提示朗读未完成，已播放内容无法撤回。重放已有播放器音频不再请求 Fish。

朗读按钮仅保留在每轮最后的主 Agent 回复旁。浏览器只传轮次，后端从原始 history 选择最终回答，跳过中间思考、工具记录和代码块；再通过当前聊天模型整理成口播稿。模型收到完整的最终回答，以保留结论之外的重要条件和例外；不会收到中间工具调用。音频准确性不作为法律结论的证据。

Gradio 自身会使用临时媒体文件，录音不是宣称完全无落盘；合成缓存与 `workspace` 已被 Git 忽略。音频识别在本机，朗读内容会发送 Fish 云端。独立 ASR 服务仅监听本机，客户端携带固定本机请求头，不可当作已鉴权的公网服务发布。

## 已验证

- 安装项目环境、Python 编译检查和实际 Gradio 页面构建／事件绑定通过；不依赖 LLM 请求验证语音模块。
- 专用 ASR 服务使用当前 SenseVoice 权重，把 WAV 识别为“好的，你说。”，耗时约 0.52 秒。
- 初次集成时原数学声线生成“你好，我是你的政策研究助手。请告诉我，你想了解哪个地区的政策？”，耗时约 3.44 秒、音频 5.06 秒；产物 `src/workspace/voice/integration-preview.wav`。
- 现已切换“政策解读女声”（Fish 同名结果中的首个已训练版本），实际启动 `http://127.0.0.1:7860`。浏览器合成政策咨询示例约 8.91 秒，播放进度正常推进；上传音频识别并填入主输入框成功。
- 未运行全量测试套件；未进行真人麦克风浏览器录音、模型实际政策研究和全流程主观听审。

入口：`src/voice/config.py`、`client.py`、`fish.py`、`asr_service.py`、`ui.py`；页面接线位于 `src/agent/webui.py`。该集成不改变现有 LLM、搜索或研究流程。

2026-10-07 界面更新：通过真实浏览器验证回复旁的朗读按钮、Fish 合成与播放；麦克风入口已接线到录音结束自动识别。当前自动化浏览器无实体麦克风，真人录音验收待用户操作。样式和桥接：`src/agent/assets/voice_controls.js`、`webui_theme.css`。

2026-10-07：切换政策解读女声；使用后端最终回答提取与逐段流式合成。真实浏览器已验证多段连续播放，结论提取样例排除了分析、思考和依据。

一次未命中缓存的分段实测：首段在 5.56 秒就绪（音频 9.05 秒），第二段在 10.32 秒就绪（音频 7.57 秒）；第二段可在第一段播放结束前备好。该数值是单次观测，不代表服务时延保证。

## 口播整理（2026-10-07）

`src/voice/narration.py` 在 Fish 之前调用当前模型，把最终回答整理为自然短句；移除证据开场、来源清单、引用标记、附件/网页编号和表格外观，保留结论中的关键数字、适用条件、例外和不确定性。文字回复本身不变。DeepSeek 整理调用关闭思考模式，不带工具，超时 35 秒且不自动重试；失败或返回截断内容时不回退朗读原文。

首次朗读增加一次模型整理等待；之后仍按短段边播放边合成。口播稿按原文、提示词版本、模型及地址缓存于 `src/workspace/voice/narration-cache/*.json`，24 小时有效、最多 128 份，已忽略 Git；文件中的 `speech` 就是实际交给 TTS 的文字，方便排查。播放条重放无需再调用模型。

模型整理是语义改写，不能保证绝无遗漏；屏幕上的完整文字仍保留供核对。配置依据：[DeepSeek 思考模式文档](https://api-docs.deepseek.com/guides/thinking_mode/)。

## 首句预生成（2026-10-07）

新回答完成后，自动在后台整理口播稿并只合成首句，不自动播放，不生成后续音频。点击朗读后直接发送已准备好的首句，在播放时继续生成余下短段。如果点击早于预生成完成，会等待同一个任务，不重复调用模型或 TTS。历史对话未预热时仍按需准备。

`src/voice/prepared.py` 按回答、声线、模型和提示词共享准备任务，首句保持独立分段，缓存约 32 条、24 小时。切换会话会取消尚未开始的预生成；正在调用的首句可能完成并进入缓存，但不会自动继续后文或播放。朗读失败仍可点击重试。
