# Xiaochi Agent

Xiaochi is a government tax-work assistant built on the 3wagent core. It helps staff query tax policies, read uploaded materials, draft consultation replies and check calculations. Mainland China is the default jurisdiction; foreign jurisdictions are considered when requested.

[简体中文](README.zh-CN.md) · [Runtime guide](src/README.md) · [Architecture](src/docs/architecture.md) · [Capability roadmap](src/docs/agent-capability-roadmap.md)

## Features

- Home shortcuts cover tax, foreign-exchange, and commerce/development matters, with four editable question starters per category. The larger composer removes repeated labels and the standalone footer; completed answers retain the reference notice.
- Blue-and-red workspace with a navy history sidebar, a central chat panel, and official resources on wide screens. Subtle entry, hover and waiting animations respect reduced-motion preferences; uploads, policy links and answer copying remain available.
- Three contextual follow-up questions after each answer. Clicking fills the editable composer; restored history retains the same questions.
- PDF, DOCX, spreadsheet, CSV and text parsing, with up to five attachments per question and 25 MB per file.
- Direct conclusions with relevant conditions and policy evidence. Initial clarification asks for at most three key facts. Reports and reply drafts are generated when requested.
- Final answers only in Web and CLI. Reasoning, tool calls, tool responses and specialist messages stay on the backend; history restoration uses a separate public transcript.
- While waiting, the Web interface shows actual execution stages and elapsed seconds, without exposing reasoning or tool arguments. The Chinese agent name is 小弛.

Every final answer receives this programmatically appended disclaimer:

> 以上内容由 AI 生成，仅供参考，具体请以现行有效政策及主管税务机关确认口径为准。

## Deployment guide

The main steps below use macOS / Linux and run from the repository root. Python 3.12 is recommended; the project requires Python 3.11 or newer. Configuration was checked on 2026-10-12. See the [full Chinese deployment tutorial](README.zh-CN.md#详细部署教程) for platform-specific installation, optional ASR, and troubleshooting.

### 1. Prepare the environment

| Features | Requirements | Processes |
|---|---|---|
| Chat, attachments and native search | DeepSeek API key | Web |
| Answer narration | DeepSeek key and Fish key | Web |
| Microphone input | Matching external SenseVoice project, environment and models | Web + ASR |

Cloud chat does not require a local LLM, Node.js, frontend compilation, Docker, a database, or the former search daemon. Narration and microphone input are separate optional features.

Install Git and [uv](https://docs.astral.sh/uv/getting-started/installation/). On macOS with Homebrew:

```bash
brew install git uv
```

On Ubuntu / Debian:

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates python3 libsndfile1
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

Then clone the repository and install its locked dependencies:

```bash
git clone https://github.com/SegemiPL/xiaochi.git xiaochi-agent
cd xiaochi-agent
uv python install 3.12
uv sync --project src --python 3.12 --locked
src/.venv/bin/python --version
```

The runtime manifest and lockfile are `src/pyproject.toml` and `src/uv.lock`. Always use `--project src`; the environment is created at `src/.venv/`. No activation is required. Add `--extra dev` for tests, or `--extra legacy-excel` for legacy `.xls` files. Retain all needed extras on subsequent sync commands.

### 2. Import API keys

Get a key from the [DeepSeek console](https://platform.deepseek.com/api_keys). Narration also needs a separate [Fish key](https://docs.fish.audio/developer-guide/getting-started/api-key). Copy the credential-free template without overwriting an existing `.env`:

```bash
if [ ! -f .env ]; then cp .env.example .env; fi
chmod 600 .env
nano .env
```

Replace the placeholders with your own values:

```dotenv
DEEPSEEK_API_KEY=your-deepseek-api-key
FISH_AUDIO_API_KEY=your-fish-api-key
```

Leave the Fish field empty for text-only use. The root `.env` is loaded automatically by Web, CLI and search; it must be next to the root README, not inside `src/`. Existing process variables take precedence, variable interpolation is disabled, and edits require restarting Web. Private `.env`, `.env.*`, and `.local/` files are ignored by Git; `.env.example` is explicitly allowed.

Check configuration without printing credentials or calling an API:

```bash
src/.venv/bin/python - <<'PY'
import os
from src.config.env import load_project_env
from src.config.llm import load_llm_config
from src.voice.config import api_key
load_project_env()
print('DeepSeek configured:', bool(os.getenv('DEEPSEEK_API_KEY')))
print('Fish configured:', bool(api_key()))
config = load_llm_config()
print('Chat model:', config['model'])
print('Chat endpoint:', config['model_server'])
PY
```

Chat and native search share `DEEPSEEK_API_KEY`, but use independent model and endpoint settings. Current chat defaults are `deepseek-flash` and `https://api.deepseek.com`, configured in `src/config/llm.yaml`; `--model` overrides chat only. Search defaults to `deepseek-v4-flash` through the Anthropic-compatible Messages endpoint, configurable with `DEEPSEEK_SEARCH_MODEL` and `DEEPSEEK_SEARCH_BASE_URL`. Selecting Kimi or local chat does not replace DeepSeek search.

For key files, Fish accepts `FISH_AUDIO_API_KEY_FILE`. DeepSeek's `DEEPSEEK_API_KEY_FILE` is imported only by `scripts/start-web.sh`; direct `python -m src.main` does not read that file setting. The Web script can also use `.local/deepseek-api-key.txt` and then the adjacent education project's file when no file path was specified. Prefer an explicit root `.env` for a new installation. See [runtime configuration](src/README.md) for other providers and search/proxy variables.

### 3. Start Web or CLI

```bash
# Web: http://127.0.0.1:8000
src/.venv/bin/python -m src.main

# Explicit host and port
src/.venv/bin/python -m src.main --host 127.0.0.1 --port 8000

# Launcher with the same port
bash scripts/start-web.sh --port 8000

# Terminal interface
src/.venv/bin/python -m src.main --cli
```

Direct startup defaults to **8000**; the Web script defaults to **7860**. Only the script reads `XIAOCHI_PORT`; both accept `--port`. ASR uses **8772**. Stop foreground services with `Ctrl+C`, then rerun after configuration changes. Previewing the page does not require a key, but submitting a question does.

Check the Web configuration endpoint:

```bash
curl --noproxy '*' http://127.0.0.1:8000/api/config
```

A JSON response establishes Web availability, not model connectivity. Then ask the UI to calculate an exclusive-of-tax amount from a supplied inclusive amount of 1130 and a supplied rate of 13%: the expected amounts are 1000 and 130. This calls the model; test official-source search separately with a policy question.

### 4. Optional narration and microphone input

**Narration:** set `FISH_AUDIO_API_KEY`, restart Web, and click the answer's speaker control. ASR is unnecessary for narration. The code uses Fish `s2.1-pro-free` and does not fall back to a paid model. Optional `.env` settings:

```dotenv
FISH_VOICE_ID=0d6320cfd92647df829a687a7b586f8a
FISH_VOICE_NAME=政策解读女声
```

The current chat model prepares spoken text; Fish synthesizes it. After an answer, the backend attempts to prepare the first sentence, without playing it. Subsequent audio is generated after playback is requested. The visual AI-reference notice is excluded from speech; original answers remain available. A narration failure does not prevent text answers.

**Microphone input:** ASR is local SenseVoice ONNX on CPU and needs no recognition API key. This repository depends on a separate `one2one-education` checkout that is not bundled or automatically downloaded. Obtain a matching checkout from the maintainer, including `prototypes/voice/engine.py`, its `requirements.lock`, and its model-download script. In that project's root:

```bash
cd /absolute/path/one2one-education
uv venv --python 3.12 .venv-voice
uv pip install --python .venv-voice/bin/python -r prototypes/voice/requirements.lock
.venv-voice/bin/python -m prototypes.voice.scripts.download_models
```

The required SenseVoice folder under `.data/voice-models/` is `sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17`, containing `model.int8.onnx` and `tokens.txt`. No education-project TTS weights are required.

In a second terminal, return to Xiaochi's root:

```bash
cd /absolute/path/xiaochi-agent
export VOICE_ASR_REPO=/absolute/path/one2one-education
export VOICE_ASR_PYTHON="$VOICE_ASR_REPO/.venv-voice/bin/python"
bash scripts/start-asr.sh
```

The ASR script does **not** load `.env`: supply paths through shell exports or `.local/voice.json` (`asr_repo`). If system `python3` is unavailable, use `"$VOICE_ASR_PYTHON" -m src.voice.asr_service` directly after setting the variables. Web defaults to `http://127.0.0.1:8772`; `VOICE_ASR_URL` changes the Web target, not the ASR listener.

```bash
curl --noproxy '*' http://127.0.0.1:8772/api/status
```

Confirm `asr.ready` is `true`, allow microphone access, record a short phrase and verify its transcription before sending. Recording requires localhost or HTTPS and is limited to about 60 seconds. See the [voice guide](src/docs/voice.md) and [Chinese ASR setup](README.zh-CN.md#6-准备并启动本地语音输入可选).

### 5. Linux service and remote access

Install the code and dependencies first. For systemd, create `/etc/systemd/system/xiaochi-web.service` with an existing service account and the correct absolute paths. The account must read `.env` and write `src/workspace/` and `src/reports/`:

```ini
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

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now xiaochi-web
sudo systemctl status xiaochi-web
journalctl -u xiaochi-web -f
# After editing .env:
sudo systemctl restart xiaochi-web
```

Web loads its root `.env`; do not embed keys in the unit. Optional ASR needs a separate unit using its own Python, the Xiaochi working directory, and `Environment=VOICE_ASR_REPO=/absolute/path/one2one-education`.

For personal remote access, leave Web bound to loopback and run on your computer:

```bash
ssh -N -L 8080:127.0.0.1:8000 your-user@your-server
```

Keep the tunnel open and browse [http://127.0.0.1:8080](http://127.0.0.1:8080). Only Web needs forwarding; its backend contacts ASR on the server. The current application shares local history and has no account/department isolation. It serializes Agent requests within one process; do not add multiple workers. An internal HTTPS reverse proxy does not change these limitations.

### 6. Windows, updates and troubleshooting

Windows text deployment uses PowerShell with Git installed:

```powershell
winget install --id=astral-sh.uv -e
# Reopen PowerShell after installation
git clone https://github.com/SegemiPL/xiaochi.git xiaochi-agent
cd xiaochi-agent
uv python install 3.12
uv sync --project src --python 3.12 --locked
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
.\src\.venv\Scripts\python.exe -m src.main --port 8000
```

Use `--cli` for terminal mode. Bash/systemd instructions apply to macOS / Linux; Windows voice dependencies require separate validation.

Before updating, preserve local changes and data, then run:

```bash
git status --short
git pull --ff-only
uv sync --project src --python 3.12 --locked
```

Restart Web and optional ASR. Keep `src/workspace/`, `src/reports/`, `.env` and `.local/` when migrating. Deleting history moves records into `.trash/`; it does not purge uploads or run logs.

| Symptom | Check |
|---|---|
| Missing packages | Run from the root with `src/.venv/bin/python`; sync `--project src` |
| Lock mismatch | Use code and `src/uv.lock` from the same revision |
| Port already in use | Stop your previous service or select another `--port` |
| Model unconfigured | Root `.env`, nonempty DeepSeek key, restart, process-variable precedence |
| DeepSeek 401 / 402 / 429 | Key / balance / rate limit; [official error codes](https://api-docs.deepseek.com/quick_start/error_codes/) |
| Search fails while chat works | Independent search endpoint/model, API access and network |
| Fish fails | Separate Fish key, voice access, model quota and connection to `api.fish.audio` |
| ASR not ready | Matching external environment and downloaded SenseVoice files |
| Microphone unavailable | Browser permission and localhost/HTTPS origin |
| Proxy breaks local access | Set `NO_PROXY=localhost,127.0.0.1,::1` |
| Application busy | Wait for the active Agent request; execution is serialized |

## Architecture and configuration

```text
Independent HTML/CSS/JavaScript frontend
    → FastAPI → ChatService → MainAgent (qwen-agent)
        ├─ Attachment parsing and targeted reading
        ├─ Configuration and official-source registries
        ├─ DeepSeek native web search
        └─ Optional specialist tasks
    → Final-answer extraction and AI-reference disclaimer
```

The former Gradio frontend and legacy search daemon have been removed. Internal conversation context, attachments and optional specialist capabilities continue to use the Agent core. There is no mandatory research pipeline.

Ordinary consultation targets about 300 Chinese characters. Operation questions with missing key facts receive clarification before targeted research. Search and DeepSeek relevance review use lower reasoning effort while the main answer retains its configured reasoning settings. New answers and restored history share Markdown rendering with support for bold text adjacent to Chinese punctuation.

| Configuration | Purpose |
|---|---|
| [src/config/xiaochi.yaml](src/config/xiaochi.yaml) | Identity, default jurisdiction, scenarios, answer style, suggested questions and disclaimer |
| [src/config/llm.yaml](src/config/llm.yaml) | DeepSeek, Kimi and local chat providers |
| [src/config/jurisdictions.yaml](src/config/jurisdictions.yaml) | Jurisdictions and official-domain policy |
| [src/config/output-contract.yaml](src/config/output-contract.yaml) | Tax-work report structure, applied when requested |
| [src/templates/report.md](src/templates/report.md) | Report and reply-draft template |

## Search and evidence boundaries

Search uses DeepSeek Harness's `web-search-deepseek` Messages protocol with native `web_search_20250305`. Only structured sources and URL-associated citation excerpts are accepted. Generated summaries are not scraped for links, and search never falls back to DuckDuckGo, Bing or SearXNG.

`WebSearchTool` reads relevant official HTML articles after discovery and returns source text, final URL, read time, content hash and truncation status. It reads up to three pages concurrently, tries other official candidates after failures, and caches successful reads in memory for 15 minutes. Titles, URLs and generated summaries alone do not establish policy provisions.

The main Agent retains autonomous tool selection and optional specialist delegation. The three-request shared limit and forced finalization on URL-only results have been removed. It stops once evidence suffices for the scoped question; progress messages report actual execution stages. Existing per-agent search protection and duplicate-query checks remain.

**Live check on 2026-10-07:** The dividend-policy question retrieved official text and correctly identified Announcement 2026 No. 27, its September 1 execution date, the covered individuals and enterprises, the 20% rate and repeal of the previous provision. This verifies one case, not general tax-policy accuracy.

Remote PDFs, JavaScript-dependent pages and a local policy-text index remain unsupported. Uploaded PDFs support page-level reading. Unreadable sources and matters unspecified by the text are reported as specific evidence gaps.

## Testing and iteration

Install development dependencies and run offline regression tests:

```bash
uv sync --project src --python 3.12 --locked --extra dev
src/.venv/bin/python -m pytest -q src/tests
```

Run the opt-in live DeepSeek behavior evaluation:

```bash
src/.venv/bin/python -m src.evals.xiaochi_smoke
```

This command consumes API usage and uses isolated temporary conversations. It writes a report to `src/workspace/eval/xiaochi-smoke.json` without keys, headers or full model configuration.

| Validation | Latest evidence |
|---|---|
| Offline regression | 220 tests passed on 2026-10-12 |
| Live model checks | 8/8 passed: identity, supplied-input calculation, follow-up rewriting, tax-input clarification, cross-border operation clarification, attachments, official-link discovery and document/date/scope verification for a recent-policy question |
| Browser checks | Desktop and mobile layout, waiting indicator, final answers and history restoration checked; real calculation and Chinese bold rendering verified |

Latest checks: initial clarification took 2.13 seconds, official-link discovery 11.16 seconds, and the complete dividend-policy answer 55.24 seconds with four search-tool calls. The previous 16.22-second evidence-gap reply did not answer the question and is not a successful speed benchmark. The regression checks retrieved official clauses and the final document name, number, execution date, rate, scope and repeal.

These eight cases establish product behavior and one policy regression. The full 42-question evaluation and broader policy accuracy remain unaccepted. See the [capability roadmap](src/docs/agent-capability-roadmap.md).

## Runtime scope and data

History entries support confirmed deletion and undo. Desktop controls appear on hover or keyboard focus; touch devices show them directly. Deleting the current conversation opens a new chat, while deleting another preserves the current answer and draft. History mutations are blocked during agent execution. Removed records stay in the conversation directory's `.trash/`; uploads and run logs are retained. This is recoverable history removal, not a data purge.

This is a local single-user version, bound to `127.0.0.1` by default, without accounts or departmental permissions. Some core state remains process-global, so execution is serialized within one process. Multiple workers are not supported.

Conversations, uploads, parsed documents and logs live in Git-ignored `src/workspace/`; requested report files live in `src/reports/`. Private context and public history are persisted separately. HTTP responses expose only public messages, and static routes do not expose workspace or model configuration.

On 2026-10-08, two live cases (supplied-input calculation and synthetic material review) each produced three contextual follow-ups in the same model response. Metadata stays out of answer text, and history restores the same questions. This does not expand the tax-policy accuracy validation above.
