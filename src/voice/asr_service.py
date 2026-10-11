"""Run using the existing voice Python environment: python -m src.voice.asr_service."""
import asyncio
import sys
from pathlib import Path

from .config import settings

# Reuse the installed SenseVoice model and runtime without starting education/TTS.
repo = Path(settings()['asr_repo']).expanduser().resolve()
if not (repo / 'prototypes/voice/engine.py').is_file():
    raise RuntimeError('Set VOICE_ASR_REPO to the one2one-education repository.')
sys.path.insert(0, str(repo))
from prototypes.voice.engine import LocalSpeechEngine, VoiceError, MAX_AUDIO_BYTES
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])
engine = LocalSpeechEngine()


@app.exception_handler(VoiceError)
async def voice_error(request, error):
    return JSONResponse({'message': error.message, 'code': error.code}, status_code=error.status)


@app.get('/api/status')
def status():
    return {'asr': engine.status()['asr'], 'service': 'xiaochi-asr'}


@app.post('/api/asr')
async def transcribe(request: Request):
    if request.headers.get('x-voice-lab') != '1' or request.headers.get('origin'):
        raise VoiceError('FORBIDDEN', '请通过应用后端识别录音。', 403)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_AUDIO_BYTES:
            raise VoiceError('TOO_LARGE', '录音过大，请缩短至 60 秒以内。', 413)
    text, duration = await asyncio.to_thread(engine.transcribe, bytes(body))
    return {'text': text, 'duration_ms': duration, 'requires_confirmation': True}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8772, access_log=False)
