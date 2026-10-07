"""API end-to-end tests with a deliberately noisy agent and real persisted histories."""

from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from qwen_agent.llm.schema import ASSISTANT, FUNCTION, FunctionCall, Message
from src.agent.conversations import ConversationStore
from src.config.product import DISCLAIMER
from src.web.app import create_app
from src.web.service import _RUN_LOCK


class NoisyAgent:
    name = '小弛'
    calls: ClassVar[list] = []

    def run(self, history):
        self.calls.append(history)
        plan = Message(ASSISTANT, 'PRIVATE_PLAN', name=self.name, reasoning_content='PRIVATE_THINK')
        call = Message(ASSISTANT, '', name=self.name,
                       function_call=FunctionCall(name='WebSearchTool', arguments='{"query":"PRIVATE_QUERY"}'))
        tool = Message(FUNCTION, 'PRIVATE_TOOL', name='WebSearchTool')
        specialist = Message(ASSISTANT, 'PRIVATE_SPECIALIST', name='rag_subagent')
        yield [plan]
        yield [plan, call, tool, specialist]
        yield [plan, call, tool, specialist, Message(ASSISTANT,
            '可参考以下政策：[政策依据](https://www.chinatax.gov.cn/)\n\n<script>alert(1)</script>', name=self.name)]


@pytest.fixture
def web(tmp_path):
    store = ConversationStore(tmp_path / 'conversations')
    NoisyAgent.calls = []
    app = create_app(store=store, agent_factory=NoisyAgent, upload_root=tmp_path / 'uploads')
    with TestClient(app) as client:
        conversation = client.post('/api/conversations').json()['id']
        yield client, conversation, store


def test_only_completed_final_answer_crosses_api_boundary_and_history_restore(web):
    client, conversation, store = web
    url = f'/api/conversations/{conversation}/messages'
    response = client.post(url, json={'message': '查询政策'})
    assert response.status_code == 200
    result = response.json()
    assert 'PRIVATE' not in response.text
    assert result['answer'].endswith(DISCLAIMER) and result['answer'].count(DISCLAIMER) == 1
    assert '<script>' not in result['answer_html']
    assert 'https://www.chinatax.gov.cn/' in result['answer_html']
    raw = store.load(conversation)
    assert 'PRIVATE_TOOL' in str(raw['messages'])
    restored = client.get(f'/api/conversations/{conversation}').json()
    assert len(restored['messages']) == 2
    assert 'PRIVATE' not in str(restored)
    assert 'messages' not in client.get('/api/conversations').json()['conversations'][0]
    client.post(url, json={'message': '继续说明适用条件'})
    assert len(NoisyAgent.calls) == 2
    assert any(message.content == 'PRIVATE_TOOL' for message in NoisyAgent.calls[1])


def test_upload_contents_remain_private_and_private_context_retains_parsed_attachment(web, monkeypatch, tmp_path):
    from src.attachments import storage
    from src.config.attachments import AttachmentSettings
    monkeypatch.setattr('src.agent.attachments.ATTACHMENT_SETTINGS', AttachmentSettings(
        storage_dir=str(tmp_path / 'parsed')))
    client, conversation, store = web
    upload = client.post(f'/api/conversations/{conversation}/attachments',
                         files={'file': ('办税材料.txt', b'PRIVATE_UPLOAD', 'text/plain')})
    assert upload.status_code == 201
    assert set(upload.json()) == {'id', 'name'}
    upload_id = upload.json()['id']
    result = client.post(f'/api/conversations/{conversation}/messages',
                         json={'message': '请解读材料', 'attachments': [upload_id]})
    assert result.status_code == 200
    raw = store.load(conversation)
    assert 'PRIVATE_UPLOAD' in str(raw['messages'])
    assert 'PRIVATE_UPLOAD' not in str(raw['public_messages'])
    restored = client.get(f'/api/conversations/{conversation}').json()
    assert restored['messages'][0]['attachments'] == ['办税材料.txt']
    assert 'PRIVATE_UPLOAD' not in str(restored)
    assert storage.session_document_ids() == []


def test_foreign_conversation_cannot_reference_another_upload(web):
    client, conversation, _ = web
    upload = client.post(f'/api/conversations/{conversation}/attachments',
                         files={'file': ('note.txt', b'private', 'text/plain')}).json()
    other = client.post('/api/conversations').json()['id']
    response = client.post(f'/api/conversations/{other}/messages',
                           json={'message': '解读', 'attachments': [upload['id']]})
    assert response.status_code == 400 and 'private' not in response.text


def test_failure_does_not_publish_partial_frame_or_expose_exception(web):
    client, conversation, store = web
    class FailingAgent(NoisyAgent):
        def run(self, history):
            yield [Message(ASSISTANT, 'PRIVATE_PARTIAL')]
            raise RuntimeError('PRIVATE_KEY /private/workspace/tool.log')
    client.app.state.chat_service.agent_factory = FailingAgent
    response = client.post(f'/api/conversations/{conversation}/messages', json={'message': '问题'})
    assert response.status_code == 502 and 'PRIVATE' not in response.text
    assert store.load(conversation)['messages'] == []
    assert client.get(f'/api/conversations/{conversation}').json()['messages'] == []


def test_busy_request_does_not_overlap_global_runtime_state(web):
    client, conversation, _ = web
    _RUN_LOCK.acquire()
    try:
        response = client.post(f'/api/conversations/{conversation}/messages', json={'message': '问题'})
        assert response.status_code == 409 and not NoisyAgent.calls
    finally:
        _RUN_LOCK.release()


def test_legacy_conversation_restores_only_public_content(web):
    client, _, store = web
    conversation = store.create([
        {'role': 'user', 'content': '问题'},
        {'role': 'assistant', 'content': 'PRIVATE_PLAN'},
        {'role': 'function', 'content': 'PRIVATE_TOOL'},
        {'role': 'assistant', 'content': '最后结论', 'reasoning_content': 'PRIVATE_THINK'},
    ])
    response = client.get(f'/api/conversations/{conversation}')
    assert response.status_code == 200 and 'PRIVATE' not in response.text
    assert '最后结论' in response.text


def test_input_validation_and_no_private_static_routes(web):
    client, conversation, _ = web
    assert client.post(f'/api/conversations/{conversation}/messages', json={'message': ' '}).status_code == 400
    assert client.post(f'/api/conversations/{conversation}/messages', json={'message': 'x' * 20_001}).status_code == 422
    assert client.post(f'/api/conversations/{conversation}/attachments',
                       files={'file': ('run.py', b'print(1)', 'text/plain')}).status_code == 400
    assert client.post(f'/api/conversations/{conversation}/attachments',
                       files={'file': ('empty.txt', b'', 'text/plain')}).status_code == 400
    assert client.get('/workspace/conversations').status_code == 404
    assert client.get('/docs').status_code == 404
    assert client.post('/api/conversations', headers={'Origin': 'https://other.example'}).status_code == 403
    assert client.get('/').status_code == 200
    assert client.get('/static/app.js').status_code == 200


def test_tax_product_identity_and_role(web):
    from src.prompts.prompts import MAIN_AGENT_SYS_PROMPT
    client, _, _ = web
    config = client.get('/api/config').json()
    assert config['name'] == '小弛'
    assert len(config['quick_questions']) == 4
    assert '政府税务部门' in MAIN_AGENT_SYS_PROMPT
    assert '默认讨论中国内地' in MAIN_AGENT_SYS_PROMPT
    assert '我准备检索' in MAIN_AGENT_SYS_PROMPT


def test_missing_model_key_returns_actionable_public_error(web):
    from src.config.llm import MissingAPIKeyError
    client, conversation, store = web

    def missing_config():
        raise MissingAPIKeyError('PRIVATE_CONFIG /private/config.yaml')

    client.app.state.chat_service.agent_factory = missing_config
    response = client.post(f'/api/conversations/{conversation}/messages', json={'message': '问题'})
    assert response.status_code == 503
    assert '服务尚未配置模型' in response.json()['detail']
    assert 'PRIVATE' not in response.text
    assert store.load(conversation)['messages'] == []


def test_chinese_bold_is_rendered_in_new_answer_and_restored_history(web):
    client, conversation, _ = web

    class BoldAgent:
        name = '小弛'

        def run(self, history):
            yield [Message(ASSISTANT, '**请补充信息：**①买方身份；参见**《政策》（文号）**。', name=self.name)]

    client.app.state.chat_service.agent_factory = BoldAgent
    response = client.post(f'/api/conversations/{conversation}/messages', json={'message': '问题'})
    assert '<strong>请补充信息：</strong>①' in response.json()['answer_html']
    restored = client.get(f'/api/conversations/{conversation}').json()
    assert '<strong>请补充信息：</strong>①' in restored['messages'][-1]['html']
    assert '<strong>《政策》（文号）</strong>' in restored['messages'][-1]['html']


def test_progress_is_visible_during_execution_and_contains_only_stage_labels(web):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from uuid import uuid4

    from src.agent.progress import report_progress

    client, conversation, _ = web
    started, release = Event(), Event()
    request_id = str(uuid4())

    class ProgressAgent(NoisyAgent):
        def run(self, history):
            report_progress('searching')
            report_progress('PRIVATE_QUERY')  # Unrecognized values are discarded.
            started.set()
            assert release.wait(5)
            yield from super().run(history)

    client.app.state.chat_service.agent_factory = ProgressAgent
    progress_url = f'/api/conversations/{conversation}/progress/{request_id}'
    with ThreadPoolExecutor() as pool:
        answer = pool.submit(client.post, f'/api/conversations/{conversation}/messages',
                             json={'message': '问题', 'request_id': request_id})
        try:
            assert started.wait(5)
            snapshot = client.get(progress_url)
            assert snapshot.status_code == 200
            assert snapshot.json()['message'] == '小弛正在检索官方政策……'
            assert snapshot.json()['status'] == 'running'
            assert set(snapshot.json()) == {'stage', 'status', 'message', 'elapsed_seconds'}
            assert 'PRIVATE' not in snapshot.text
            assert client.get(f'/api/conversations/{conversation}').json()['messages'] == []
            other = client.post('/api/conversations').json()['id']
            assert client.get(f'/api/conversations/{other}/progress/{request_id}').status_code == 404
        finally:
            release.set()
        assert answer.result().status_code == 200
    assert client.get(progress_url).json()['status'] == 'complete'


def test_progress_failure_is_generic_and_next_request_gets_fresh_state(web):
    from uuid import uuid4

    client, conversation, _ = web
    request_id = str(uuid4())

    class FailingAgent(NoisyAgent):
        def run(self, history):
            raise RuntimeError('PRIVATE_EXCEPTION')

    client.app.state.chat_service.agent_factory = FailingAgent
    assert client.post(f'/api/conversations/{conversation}/messages',
                       json={'message': '问题', 'request_id': request_id}).status_code == 502
    snapshot = client.get(f'/api/conversations/{conversation}/progress/{request_id}')
    assert snapshot.json()['status'] == 'failed' and 'PRIVATE' not in snapshot.text
    client.app.state.chat_service.agent_factory = NoisyAgent
    next_id = str(uuid4())
    assert client.post(f'/api/conversations/{conversation}/messages',
                       json={'message': '问题', 'request_id': next_id}).status_code == 200
    assert client.get(f'/api/conversations/{conversation}/progress/{next_id}').json()['status'] == 'complete'


def test_delete_and_undo_preserve_other_histories_private_context_and_attachments(web):
    client, conversation, store = web
    url = f'/api/conversations/{conversation}'
    upload = client.post(url + '/attachments',
                         files={'file': ('note.txt', b'private material', 'text/plain')}).json()
    client.post(url + '/messages', json={'message': '查询政策'})
    original = store.load(conversation)
    other = client.post('/api/conversations').json()['id']
    other_before = store.load(other)
    assert client.delete(url).json() == {'id': conversation, 'deleted': True}
    assert client.get(url).status_code == 404
    assert [item['id'] for item in client.get('/api/conversations').json()['conversations']] == [other]
    assert client.post(url + '/messages', json={'message': '已删除'}).status_code == 404
    assert client.post(url + '/attachments',
                       files={'file': ('new.txt', b'x', 'text/plain')}).status_code == 404
    restored = client.post(url + '/restore')
    assert restored.json() == {'id': conversation, 'restored': True}
    assert 'PRIVATE' not in restored.text
    assert store.load(conversation) == original
    assert store.load(other) == other_before
    assert 'PRIVATE' not in client.get(url).text
    # Previously uploaded files remain available when a deletion is undone.
    attachment = client.app.state.chat_service.attachment(conversation, upload['id'])
    assert attachment['path'].read_bytes() == b'private material'


def test_deletion_and_undo_cannot_race_with_a_running_answer(web):
    client, conversation, store = web
    url = f'/api/conversations/{conversation}'
    original = store.load(conversation)
    _RUN_LOCK.acquire()
    try:
        assert client.delete(url).status_code == 409
        assert store.load(conversation) == original
    finally:
        _RUN_LOCK.release()
    assert client.delete(url).status_code == 200
    _RUN_LOCK.acquire()
    try:
        assert client.post(url + '/restore').status_code == 409
        assert client.get(url).status_code == 404
    finally:
        _RUN_LOCK.release()
    assert client.post(url + '/restore').status_code == 200


def test_history_mutation_errors_and_cross_origin_requests_leave_records_intact(web):
    client, conversation, store = web
    original = store.load(conversation)
    url = f'/api/conversations/{conversation}'
    assert client.delete(url, headers={'Origin': 'https://other.example'}).status_code == 403
    assert client.post(url + '/restore', headers={'Origin': 'https://other.example'}).status_code == 403
    assert client.delete('/api/conversations/not-an-id').status_code == 404
    assert client.post('/api/conversations/not-an-id/restore').status_code == 404
    assert client.post(url + '/restore').status_code == 404
    assert store.load(conversation) == original
    assert client.delete(url).status_code == 200
    assert client.delete(url).status_code == 404
    assert client.post(url + '/restore').status_code == 200
