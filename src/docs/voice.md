# ASR 与结论朗读

更新：2026-10-12。语音输入与答复朗读集成于原生 FastAPI 聊天界面；两项功能可分别部署。首次配置见[完整部署教程](../../README.zh-CN.md#详细部署教程)。

## 使用

- 输入框旁的麦克风图标开始录音，再点一次停止。最长约 60 秒，停止后本机识别并填入输入框，核对后自行发送。没有持续监听或自动提交。
- 最终答复旁的声音图标朗读该轮结论。模型先将最终回答整理成自然口播稿，去掉引用符号、文件/网页编号、表格格式和过程描述，保留关键条件与例外；页面原文不变。
- 页面末尾统一的“以上内容由 AI 生成，仅供参考”提示只显示，不朗读。口播输入、模型输出、缓存读取与分段前均过滤该提示；答复本身的适用条件、例外和不确定性保留。
- 新回答完成后只在后台预生成首句，不自动播放。点击声音图标才播放首句，同时生成下一段；未点击不会生成后续音频。
- 播放条可以暂停，声音图标可重放全文。切换对话、新建或发送问题会停止播放与后续请求。已开始的服务端单段请求可能完成并进入缓存。

## 启动

先按部署教程准备独立 `one2one-education` 的 `.venv-voice`、锁定依赖和 SenseVoice 模型；仅使用 Fish 朗读时可跳过 ASR。已准备好语音输入环境后，在仓库根目录运行：

```bash
uv sync --project src --python 3.12 --locked
export VOICE_ASR_REPO=/absolute/path/one2one-education
export VOICE_ASR_PYTHON="$VOICE_ASR_REPO/.venv-voice/bin/python"
bash scripts/start-asr.sh
```

另开终端：

```bash
bash scripts/start-web.sh --port 8000
```

上述命令明确使用8000。Web 启动脚本不传端口时默认监听 `http://127.0.0.1:7860`，可传 `--port 8000` 或设置 `XIAOCHI_PORT`。main 自带的 `python -m src.main` 默认仍为 8000。

ASR 独立监听 `127.0.0.1:8772`，复用相邻 `one2one-education` 的 SenseVoice 代码、模型和 `.venv-voice`。支持 `VOICE_ASR_REPO` / `VOICE_ASR_PYTHON`；识别地址可设置 `VOICE_ASR_URL`，仅允许本机 HTTP 地址。浏览器录音转换成单声道 WAV 后上传，识别用临时文件在请求结束时删除。

**ASR 脚本不自动加载 `.env`**；路径通过当前终端 `export` 或 `.local/voice.json` 的 `asr_repo` 设置。`VOICE_ASR_URL` 只调整 Web 请求目标，不修改 ASR 监听端口。独立 ASR 进程不继承 Web 进程加载的配置。

DeepSeek Key 优先读取进程环境、仓库 `.env`；未配置时启动脚本读取 `DEEPSEEK_API_KEY_FILE` 或 `.local/deepseek-api-key.txt`，最后复用相邻教育项目的同名文件。Key 不进入浏览器。

## Fish 配置

在根目录 `.env` 填入 `FISH_AUDIO_API_KEY=你的Fish密钥` 并重启 Web，即可启用朗读；此密钥与 DeepSeek Key 不通用。模板见[.env.example](../../.env.example)。

模型固定 `s2.1-pro-free`，不自动切付费档。当前默认声线：政策解读女声，ID `0d6320cfd92647df829a687a7b586f8a`。

环境变量 `FISH_VOICE_ID`、`FISH_VOICE_NAME` 优先于 `.local/voice.json`。示例：

```json
{
  "voice_id": "0d6320cfd92647df829a687a7b586f8a",
  "voice_name": "政策解读女声",
  "key_file": "~/code/one2one-education/.local/fish-api-key.txt",
  "asr_repo": "~/code/one2one-education",
  "asr_url": "http://127.0.0.1:8772"
}
```

Fish Key 读取 `FISH_AUDIO_API_KEY` / `FISH_API_KEY`，或 `FISH_AUDIO_API_KEY_FILE`，或上述 `key_file`。配置文件每次请求读取，改声线后会重新准备首句。声线选择不影响教育项目。

## 缓存和边界

- `src/voice/narration.py` 使用当前聊天模型整理口播稿，DeepSeek 整理调用关闭思考，不使用工具。失败不回退朗读原文。
- `src/workspace/voice/narration-cache/*.json` 的 `speech` 就是 TTS 文本；按原文、提示词、模型缓存，24 小时有效，最多 128 份。模型改写仍可能遗漏，完整文字保留供核对。
- `src/voice/prepared.py` 共享首句准备任务。提前点击只等待同一任务；内存约 32 份、24 小时。其余音频按需生成。
- Fish WAV 缓存位于 `src/workspace/voice/audio-cache`，容量 128 MiB、24 小时空闲过期，键包含模型、声线、文本、语速。重放命中缓存不再推理。
- 首句和后续每段仍受网络与上游延迟影响，不保证无间隙。ASR 在本机，口播整理和合成分别发送到配置的模型与 Fish。
- 新接口沿用 main 的同源写请求保护；这是本机工具，不是已具备用户鉴权的公网服务。

入口：`src/web/voice.py`、`src/web/static/voice.js`、`src/voice/`。语音接口测试：`src/tests/test_voice_web.py`。
