"""Native Web voice boundary preserves public-answer and on-demand semantics."""
from unittest.mock import Mock

from fastapi.testclient import TestClient

from src.agent.conversations import ConversationStore
from src.web.app import create_app
from src.web import voice


def test_voice_uses_public_history_and_only_generates_requested_tail(tmp_path, monkeypatch):
    store = ConversationStore(tmp_path)
    conversation = store.create()
    store.save(conversation, [], public_messages=[
        {'role': 'user', 'content': '问题'},
        {'role': 'assistant', 'content': '公开结论'},
    ])
    prepare = Mock(return_value=(['首句。', '后句。'], {'name': '政策解读女声'}, b'first'))
    synth = Mock(return_value=b'second')
    monkeypatch.setattr(voice.prepared, 'prepare', prepare)
    monkeypatch.setattr(voice.prepared, 'synthesize_chunk', synth)
    monkeypatch.setattr(voice, 'get_active_llm_config', lambda: {'model': 'test'})
    with TestClient(create_app(store=store)) as client:
        body = {'conversation_id': conversation, 'turn': 0}
        assert client.post('/api/voice/prepare', json=body).json()['segments'] == 2
        assert not synth.called
        assert prepare.call_args.args[0][1]['content'].startswith('公开结论')
        assert client.post('/api/voice/segment', json=body).content == b'first'
        assert not synth.called
        assert client.post('/api/voice/segment', json={**body, 'segment': 1}).content == b'second'
        synth.assert_called_once()
        assert client.post('/api/voice/segment', json={**body, 'segment': 2}).status_code == 422
        assert client.post('/api/voice/prepare', json=body,
                           headers={'origin': 'https://other.example'}).status_code == 403


def test_asr_temporary_recording_is_removed(tmp_path, monkeypatch):
    paths = []
    def transcribe(path):
        paths.append(path)
        assert path.read_bytes() == b'audio'
        return '识别文字'
    monkeypatch.setattr(voice.client, 'transcribe', transcribe)
    with TestClient(create_app(store=ConversationStore(tmp_path))) as client:
        result = client.post('/api/voice/asr', files={'file': ('recording.wav', b'audio', 'audio/wav')})
        assert result.json() == {'text': '识别文字'}
    assert not paths[0].exists()
