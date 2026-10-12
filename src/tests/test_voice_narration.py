"""The visual AI notice must never enter speech; policy limits must remain."""
import hashlib
import json
from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from src.agent.conversations import ConversationStore
from src.config.product import DISCLAIMER
from src.voice import client, narration, prepared
from src.voice.text import without_ai_footer
from src.web import voice
from src.web.app import create_app

BODY = '办理期限为二十个工作日，不包括补正材料时间；不保证审批通过。'


@pytest.mark.parametrize('notice', [DISCLAIMER, '以上内容由 ai 生成，仅供参考。',
                                  '以上内容由人工智能生成，仅供参考。'])
def test_final_answer_and_chunks_exclude_notice_but_keep_conditions(notice):
    history = [{'role': 'user', 'content': '办理多久？'},
               {'role': 'assistant', 'content': BODY + '\n\n' + notice}]
    assert client.final_answer(history, 0, conclusion_only=False) == BODY
    assert ''.join(client.speech_chunks(BODY + '\n\n' + notice)) == BODY
    assert history[-1]['content'].endswith(notice)


def configure_narration(tmp_path, monkeypatch):
    config = {'model_server': 'https://api.deepseek.com', 'model': 'test', 'api_key': 'test'}
    monkeypatch.setattr(narration, 'WORK', tmp_path)
    monkeypatch.setattr(narration, 'get_active_llm_config', lambda: config)
    model = MagicMock()
    model.__enter__.return_value = model
    model.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
        finish_reason='stop', message=SimpleNamespace(content=json.dumps(
            {'speech': BODY + '\n' + DISCLAIMER}, ensure_ascii=False)))])
    monkeypatch.setattr(narration, 'OpenAI', lambda **kwargs: model)
    return config, model


def test_narration_cleans_model_input_output_and_cache(tmp_path, monkeypatch):
    _, model = configure_narration(tmp_path, monkeypatch)
    assert narration.prepare_narration(BODY + '\n\n' + DISCLAIMER) == BODY
    request = model.chat.completions.create.call_args.kwargs
    assert json.loads(request['messages'][1]['content'])['answer'] == BODY
    assert narration.prepare_narration(BODY + '\n\n' + DISCLAIMER) == BODY
    assert model.chat.completions.create.call_count == 1
    cached = json.loads(next((tmp_path / 'narration-cache').glob('*.json')).read_text())
    assert cached['speech'] == BODY


def test_cached_narration_is_filtered_without_another_model_call(tmp_path, monkeypatch):
    config, model = configure_narration(tmp_path, monkeypatch)
    identity = json.dumps([narration.PROMPT, config['model_server'], config['model'], BODY],
                          ensure_ascii=False)
    directory = tmp_path / 'narration-cache'
    directory.mkdir()
    path = directory / (hashlib.sha256(identity.encode()).hexdigest() + '.json')
    path.write_text(json.dumps({'speech': BODY + '\n' + DISCLAIMER}, ensure_ascii=False))
    assert narration.prepare_narration(BODY) == BODY
    model.chat.completions.create.assert_not_called()


def test_business_warnings_and_mentions_of_notice_are_preserved():
    text = '政策口径仅供参考，请以主管部门确认为准。不能保证适用。'
    assert without_ai_footer(text) == text
    quoted = '“以上内容由 AI 生成，仅供参考”是页面提示，不是政策依据。'
    assert without_ai_footer(quoted) == quoted
    assert without_ai_footer(BODY + DISCLAIMER + '\n' + DISCLAIMER) == BODY


def test_web_playback_excludes_footer_while_public_answer_keeps_it(tmp_path, monkeypatch):
    config, _ = configure_narration(tmp_path / 'voice', monkeypatch)
    monkeypatch.setattr(voice, 'get_active_llm_config', lambda: config)
    monkeypatch.setattr(prepared, 'get_active_llm_config', lambda: config)
    monkeypatch.setattr(prepared, '_pending', OrderedDict())
    spoken = []

    def synthesize(text, voice):
        spoken.append(text)
        return b'audio'

    monkeypatch.setattr(prepared, 'synthesize_chunk', synthesize)
    store = ConversationStore(tmp_path / 'history')
    conversation = store.create()
    store.save(conversation, [], public_messages=[
        {'role': 'user', 'content': '办理多久？'},
        {'role': 'assistant', 'content': BODY + '\n\n' + DISCLAIMER},
    ])
    with TestClient(create_app(store=store)) as web:
        body = {'conversation_id': conversation, 'turn': 0}
        count = web.post('/api/voice/prepare', json=body).json()['segments']
        assert len(spoken) == 1  # Only the first sentence is prewarmed.
        for segment in range(count):
            assert web.post('/api/voice/segment', json={**body, 'segment': segment}).content == b'audio'
        assert ''.join(spoken) == BODY
        public = web.get(f'/api/conversations/{conversation}').json()['messages'][-1]
        assert public['content'] == BODY + '\n\n' + DISCLAIMER
        assert DISCLAIMER in public['html']
