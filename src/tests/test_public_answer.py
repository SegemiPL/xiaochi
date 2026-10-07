"""Completed-turn evidence: neither live frames nor old histories leak internals."""
import pytest
from qwen_agent.llm.schema import ASSISTANT, FUNCTION, FunctionCall, Message
from src.agent.public_answer import (
    INCOMPLETE_ANSWER,
    completed_answer,
    legacy_public_history,
    public_text,
)
from src.config.product import DISCLAIMER


@pytest.mark.parametrize('last', [
    Message(FUNCTION, 'private tool result', name='WebSearchTool'),
    Message(ASSISTANT, 'private specialist', name='rag_subagent'),
    Message(ASSISTANT, '', name='小弛', reasoning_content='private thought'),
    Message(ASSISTANT, 'planning', name='小弛',
            function_call=FunctionCall(name='WebSearchTool', arguments='{}')),
    {'role': 'assistant', 'content': 'PRIVATE planning',
     'tool_calls': [{'id': 'call_pending', 'function': {'name': 'WebSearchTool'}}]},
])
def test_unfinished_turn_never_falls_back_to_prior_planning(last):
    answer = completed_answer([Message(ASSISTANT, '我准备检索 PRIVATE'), last])
    assert INCOMPLETE_ANSWER in answer
    assert 'PRIVATE' not in answer and 'planning' not in answer
    assert 'private' not in answer


def test_main_final_answer_retains_sources_but_omits_reasoning_and_duplicate_footer():
    answer = completed_answer([Message(ASSISTANT,
        f'<think>internal secret</think>结论 [政策](https://www.chinatax.gov.cn/)\n\n{DISCLAIMER}\n{DISCLAIMER}',
        name='小弛', reasoning_content='internal reasoning')])
    assert 'internal' not in answer
    assert 'https://www.chinatax.gov.cn/' in answer
    assert answer.count(DISCLAIMER) == 1


def test_unclosed_thinking_block_is_not_public_text():
    assert 'secret' not in public_text('有效文本<think>secret')


def test_legacy_projection_hides_private_upload_and_intermediate_messages():
    messages = [
        {'role': 'user', 'content': '解读文件<uploaded_document id="abc">PRIVATE_FILE</uploaded_document>'},
        {'role': 'assistant', 'content': 'PRIVATE_PLAN'},
        {'role': 'assistant', 'function_call': {'name': 'WebSearchTool'}, 'content': ''},
        {'role': 'function', 'content': 'PRIVATE_TOOL'},
        {'role': 'assistant', 'name': 'rag_subagent', 'content': 'PRIVATE_SPECIALIST'},
        {'role': 'assistant', 'name': '3wagent', 'content': '公开结论', 'reasoning_content': 'PRIVATE_THINK'},
    ]
    public = legacy_public_history(messages)
    assert len(public) == 2 and '公开结论' in public[-1]['content']
    assert 'PRIVATE' not in str(public)
