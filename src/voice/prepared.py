"""Single-flight first-sentence preparation shared by prewarm and playback."""
from collections import OrderedDict
from concurrent.futures import Future
import hashlib
import json
import threading
import time

from src.config.llm import get_active_llm_config
from . import client
from .config import MODEL, settings
from .narration import PROMPT, prepare_narration

_pending = OrderedDict()
_lock = threading.Lock()
_tts_lock = threading.Lock()


def synthesize_chunk(text, voice):
    # A speculative first sentence must not cause ENGINE_BUSY for playback.
    with _tts_lock:
        return client.engine.synthesize(text, 1.0, voice)[0]


def prepare(history, turn):
    source = client.final_answer(history, turn, conclusion_only=False)
    config = settings()
    model = get_active_llm_config() or {}
    voice = {'reference_id': config['voice_id'], 'name': config['voice_name']}
    identity = [source, voice, MODEL, PROMPT, model.get('model'), model.get('model_server')]
    key = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
    with _lock:
        # Keep at most 32 completed first sentences, expiring after 24 hours.
        for old, (created, future) in list(_pending.items()):
            if future.done() and (time.monotonic() - created > 86400 or len(_pending) > 32):
                del _pending[old]
        entry = _pending.get(key)
        owner = entry is None
        if owner:
            future = Future()
            _pending[key] = (time.monotonic(), future)
        else:
            future = entry[1]
            _pending.move_to_end(key)
    if owner:
        try:
            chunks = client.speech_chunks(prepare_narration(source))
            first_audio = synthesize_chunk(chunks[0], voice)
            future.set_result((chunks, voice, first_audio))
        except Exception as error:
            future.set_exception(error)
            with _lock:
                _pending.pop(key, None)
    # A click during preparation joins this job instead of repeating the calls.
    return future.result()


def prewarm_latest(history):
    turn = sum(message.get('role') == 'user' for message in history) - 1
    try:
        prepare(history, turn)
    except Exception:
        # Background preparation never interrupts chat; a click can retry and
        # surface a friendly error through the normal playback callback.
        pass
