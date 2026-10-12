"""Fish TTS adapter reused from one2one-education; no ASR/model imports."""

import io
import json
import hashlib
import threading
import time
import wave
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import VoiceError
from .audio_cache import AudioCache
from .config import api_key, MODEL, WORK

SAMPLE_RATE = 24000
MAX_OUTPUT_BYTES = SAMPLE_RATE * 2 * 180


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class FishSpeechEngine:
    def __init__(self, api_key=None, opener=None):
        self._key_override = api_key
        self._cache = AudioCache(WORK / 'audio-cache')
        self.cache_hits = 0
        self._opener = opener or build_opener(NoRedirect())
        self._lock = threading.Lock()

    @property
    def _key(self):
        return self._key_override if self._key_override is not None else api_key()

    def synthesize(self, text, rate, voice):
        if not self._key:
            raise VoiceError('API_KEY_MISSING', '请配置 FISH_AUDIO_API_KEY_FILE 或 FISH_AUDIO_API_KEY。', 503)
        if not self._lock.acquire(blocking=False):
            raise VoiceError('ENGINE_BUSY', '上一段语音仍在处理，请稍后重试。', 409)
        try:
            # Preserve letters, punctuation and Fish expression/phoneme tags verbatim.
            payload = {'text': text.strip(), 'reference_id': voice['reference_id'],
                'format': 'pcm', 'sample_rate': SAMPLE_RATE, 'prosody': {'speed': rate},
                'latency': 'normal', 'normalize': True}
            key = hashlib.sha256(json.dumps({'provider': 'fish-audio', 'model': MODEL,
                'payload': payload, 'version': 1}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            cached = self._cache.get(key)
            if cached:
                with wave.open(io.BytesIO(cached), 'rb') as wav:
                    duration = round(wav.getnframes() / wav.getframerate() * 1000)
                self.cache_hits += 1
                return cached, duration
            request = Request('https://api.fish.audio/v1/tts', data=json.dumps(payload).encode(), headers={
                'Authorization': f'Bearer {self._key}', 'Content-Type': 'application/json',
                'model': MODEL,
            }, method='POST')
            # No automatic retries, redirects, or paid-model fallback.
            deadline = time.monotonic() + 90
            with self._opener.open(request, timeout=20) as response:
                content_type = response.headers.get('Content-Type', '').split(';')[0].strip()
                if content_type not in ('audio/pcm', 'audio/L16', 'audio/raw', 'application/octet-stream'):
                    raise VoiceError('INVALID_UPSTREAM_AUDIO', '语音服务返回的不是预期 PCM 音频。', 502)
                pcm = bytearray()
                while True:
                    if time.monotonic() > deadline:
                        raise TimeoutError
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    pcm.extend(chunk)
                    if len(pcm) > MAX_OUTPUT_BYTES:
                        raise VoiceError('INVALID_UPSTREAM_AUDIO', '生成音频超过三分钟限制，请缩短文字。', 502)
            if not pcm or len(pcm) % 2:
                raise VoiceError('INVALID_UPSTREAM_AUDIO', '生成音频为空或不完整，请手动重试。', 502)
            output = io.BytesIO()
            with wave.open(output, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(SAMPLE_RATE)
                wav.writeframes(pcm)
            self._cache.put(key, output.getvalue())
            return output.getvalue(), round(len(pcm) / 2 / SAMPLE_RATE * 1000)
        except HTTPError as exc:
            codes = {
                401: ('FISH_AUTH', 'Fish API key 无效，请检查服务端配置。'),
                402: ('FISH_QUOTA', '免费服务或账户额度不可用；未切换付费模型。'),
                403: ('FISH_FORBIDDEN', '账户无法使用该声音或模型，请检查访问权限。'),
                404: ('FISH_NOT_FOUND', '目标声音或接口不可用。'),
                429: ('FISH_RATE_LIMIT', 'Fish 服务限流，请稍后手动重试。'),
            }
            code, message = codes.get(exc.code, ('FISH_FAILED', 'Fish 语音服务暂不可用，请稍后手动重试。'))
            exc.close()
            raise VoiceError(code, message, 502) from None
        except (TimeoutError, URLError, OSError):
            raise VoiceError('FISH_NETWORK', '连接 Fish 服务失败或超时，请检查网络后手动重试。', 504) from None
        finally:
            self._lock.release()
