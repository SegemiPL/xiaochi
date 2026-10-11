"""Follow-up metadata must remain separate from public answers and private frames."""
import pytest
from qwen_agent.llm.schema import ASSISTANT, FUNCTION, Message
from src.agent.followups import fallback_questions, normalize_questions, split_related_questions
from src.agent.public_answer import completed_answer, completed_questions, public_text
from src.config.product import DISCLAIMER

QUESTIONS = ['这项政策对适用主体有哪些要求？', '如何核对这项政策的执行日期？', '能否整理成便于核对的政策要点？']


def tagged_answer(questions=QUESTIONS):
    import json
    return '已核实的答复。\n<!-- xiaochi-related-questions\n' + json.dumps(questions, ensure_ascii=False) + '\n-->'


def test_metadata_is_parsed_without_changing_answer_or_duplicating_footer():
    frames = [Message(ASSISTANT, tagged_answer(), name='小弛')]
    assert completed_questions(frames, '查询政策') == QUESTIONS
    assert completed_answer(frames) == f'已核实的答复。\n\n{DISCLAIMER}'
    assert public_text(tagged_answer()) == completed_answer(frames)


@pytest.mark.parametrize('metadata', ['["未完', 'not json', '["重复内容？", "重复内容？", "重复内容？"]'])
def test_malformed_or_truncated_metadata_never_leaks_or_breaks_answer(metadata):
    raw = '有效正文\n<!-- xiaochi-related-questions\n' + metadata
    answer, questions = split_related_questions(raw)
    assert answer == '有效正文' and questions == []
    frames = [Message(ASSISTANT, raw, name='小弛')]
    result = completed_questions(frames, '如何计算含税金额')
    assert len(result) == 3 and len(set(result)) == 3
    assert '参数' in result[0]


@pytest.mark.parametrize('values', [None, ['问题'], ['正常的问题一？', '正常的问题二？', '<script>坏</script>'],
    ['正常的问题一？', '正常的问题二？', {'private': 'value'}]])
def test_metadata_validation_rejects_unexpected_types_or_markup(values):
    assert normalize_questions(values) == []


def test_thinking_tools_and_specialists_cannot_supply_questions():
    for frame in [Message(FUNCTION, tagged_answer(), name='WebSearchTool'),
                  Message(ASSISTANT, tagged_answer(), name='rag_subagent'),
                  Message(ASSISTANT, '<think>' + tagged_answer() + '</think>公开答复', name='小弛')]:
        questions = completed_questions([frame], '请计算税额')
        assert questions != QUESTIONS
        assert '参数' in questions[0]


def test_context_fallback_distinguishes_calculation_drafting_and_policy():
    groups = [fallback_questions(question, '') for question in ['请计算税额', '请草拟答复', '查询政策']]
    assert all(len(group) == len(set(group)) == 3 for group in groups)
    assert '计算' in ''.join(groups[0]) and '草稿' in ''.join(groups[1])
    assert '政策' in ''.join(groups[2])
