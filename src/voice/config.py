"""Server-only voice settings, independent from the education project's selection."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'src/workspace/voice'
MODEL = 's2.1-pro-free'
DEFAULT_VOICE = '0d6320cfd92647df829a687a7b586f8a'


def settings():
    path = ROOT / '.local/voice.json'
    config = json.loads(path.read_text()) if path.is_file() else {}
    return {
        'voice_id': os.getenv('FISH_VOICE_ID') or config.get('voice_id', DEFAULT_VOICE),
        'voice_name': os.getenv('FISH_VOICE_NAME') or config.get('voice_name', '政策解读女声'),
        'asr_url': os.getenv('VOICE_ASR_URL') or config.get('asr_url', 'http://127.0.0.1:8772'),
        'key_file': os.getenv('FISH_AUDIO_API_KEY_FILE') or config.get('key_file', str(ROOT / '.local/fish-api-key.txt')),
        'asr_repo': os.getenv('VOICE_ASR_REPO') or config.get('asr_repo', str(ROOT.parent / 'one2one-education')),
    }


def api_key():
    value = os.getenv('FISH_AUDIO_API_KEY') or os.getenv('FISH_API_KEY')
    if value:
        return value.strip()
    path = Path(settings()['key_file']).expanduser()
    return path.read_text().strip() if path.is_file() else ''


class VoiceError(Exception):
    def __init__(self, code, message, status=503):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
