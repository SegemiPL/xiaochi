"""On-demand voice endpoints for the native Xiaochi interface."""
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.config.llm import MissingAPIKeyError, get_active_llm_config, load_llm_config
from src.voice import client, prepared
from src.voice.config import VoiceError


class VoiceRequest(BaseModel):
    conversation_id: str
    turn: int = Field(ge=0)
    segment: int = Field(default=0, ge=0)


def install_voice(app, service):
    def get_prepared(body):
        try:
            history = service.public_record(body.conversation_id)['messages']
            if get_active_llm_config() is None:
                load_llm_config()
            return prepared.prepare(history, body.turn)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, '对话不存在。') from None
        except MissingAPIKeyError:
            raise HTTPException(503, '口播模型尚未配置。') from None
        except VoiceError as error:
            raise HTTPException(error.status, error.message) from None

    @app.post('/api/voice/prepare')
    def prepare(body: VoiceRequest):
        chunks, voice, _ = get_prepared(body)
        return {'segments': len(chunks), 'voice': voice['name']}

    @app.post('/api/voice/segment')
    def segment(body: VoiceRequest):
        chunks, voice, first = get_prepared(body)
        if body.segment >= len(chunks):
            raise HTTPException(422, '音频段不存在。')
        try:
            audio = first if body.segment == 0 else prepared.synthesize_chunk(chunks[body.segment], voice)
        except VoiceError as error:
            raise HTTPException(error.status, error.message) from None
        return Response(audio, media_type='audio/wav', headers={'Cache-Control': 'no-store'})

    @app.post('/api/voice/asr')
    async def recognize(file: UploadFile = File(...)):
        from starlette.concurrency import run_in_threadpool
        path = None
        try:
            data = await file.read(12 * 1024 * 1024 + 1)
            if not data or len(data) > 12 * 1024 * 1024:
                raise HTTPException(413, '请录制 60 秒以内的音频。')
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as target:
                target.write(data)
                path = Path(target.name)
            return {'text': await run_in_threadpool(client.transcribe, path)}
        except VoiceError as error:
            raise HTTPException(error.status, error.message) from None
        except (ValueError, RuntimeError):
            raise HTTPException(422, '录音无法读取，请重新录制。') from None
        finally:
            await file.close()
            if path:
                path.unlink(missing_ok=True)

    def prewarm(conversation_id):
        try:
            prepared.prewarm_latest(service.public_record(conversation_id)['messages'])
        except (ValueError, FileNotFoundError):
            pass  # The user may delete the conversation while preparation is queued.
    return prewarm
