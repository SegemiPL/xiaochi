"""Three short follow-up questions, separated from the completed answer."""
from __future__ import annotations

import json
import re

RELATED_QUESTIONS_PROMPT = '''
最终答复完成后，另起一行输出下面的机器可读区块。区块不属于正文，不在正文重复推荐问题：
<!-- xiaochi-related-questions
["问题一？", "问题二？", "问题三？"]
-->
生成恰好三个与本轮提问、已确认事实及最终答复紧密相关的后续问题，供用户继续提问。
使用用户提问的口吻，每条8至45字，三个角度不同，不重复已回答内容，不夹带答案。
优先针对尚需了解的适用条件、执行细节、材料或进一步计算；澄清轮应帮助补充事实。
只依据已知内容，不预设未核实政策、税率、身份或结论，不要求提供身份证号等敏感信息。
不要写泛泛的“还有什么问题”，不要为推荐问题检索、委派或增加工具调用。
区块只在本轮最终答复末尾出现一次，必须为有效 JSON 字符串数组，不用代码围栏。
'''
_MARKER = re.compile(r'<!--\s*xiaochi-related-questions\b', re.IGNORECASE)


def normalize_questions(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) != 3:
        return []
    questions = []
    for item in value:
        if not isinstance(item, str):
            return []
        item = item.strip()
        if not 6 <= len(item) <= 100 or re.search(r'[<>`\r\n]|https?://', item):
            return []
        item = item.rstrip('？?。') + '？'
        if item in questions:
            return []
        questions.append(item)
    return questions


def split_related_questions(text: str) -> tuple[str, list[str]]:
    """Even a truncated/malformed metadata block must never become answer text."""
    marker = _MARKER.search(text)
    if marker is None:
        return text, []
    body, metadata = text[:marker.start()].rstrip(), text[marker.end():]
    try:
        values = json.loads(metadata.split('-->', 1)[0].strip())
    except (ValueError, TypeError):
        return body, []
    return body, normalize_questions(values)


def fallback_questions(question: str, answer: str) -> list[str]:
    """Contextual prompts for old histories or missing model metadata; no policy claims."""
    context = question + '\n' + answer
    if any(word in context for word in ('无法读取', '无法形成', '未能形成')):
        return ['需要补充哪些信息才能继续分析？', '这份材料可以换成哪些支持的格式？', '可以先根据已提供的信息说明哪些内容？']
    if any(word in question for word in ('计算', '税额', '含税', '税费核算')):
        return ['上述计算中哪些参数需要进一步核对？', '如果金额发生变化，应如何重新计算？', '能否将上述计算过程整理成核对表？']
    if any(word in question for word in ('草拟', '起草', '改写', '文稿', '答复草稿')):
        return ['这份草稿中哪些表述需要核实政策依据？', '能否将这份草稿改写得更简洁、规范？', '正式使用这份草稿前需要核对哪些事项？']
    if any(word in context for word in ('材料', '附件', '文件内容')):
        return ['这份材料中还有哪些信息需要补充？', '能否把上述材料要点整理成核对清单？', '材料中的时间和适用条件应如何核实？']
    if any(word in context for word in ('政策', '公告', '规定', '适用')):
        return ['判断上述政策是否适用，还需确认哪些事实？', '如何核对上述政策的执行时间和有效状态？', '能否将上述政策依据与适用条件整理成表格？']
    return ['继续分析上述问题，还需要补充哪些事实？', '上述事项中哪些内容需要进一步核实？', '能否将上述答复整理成便于核对的要点？']
