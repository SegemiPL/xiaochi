"""Chinese emphasis regression without changing code, escaping or HTML safety."""

import pytest
from src.web.markdown import render_answer


@pytest.mark.parametrize(('source', 'expected'), [
    ('**请补充三项关键信息：**①购房人身份', '<strong>请补充三项关键信息：</strong>①'),
    ('按**13%**计算', '<strong>13%</strong>计算'),
    ('**结论**：先确认', '<strong>结论</strong>：'),
    ('**加粗 [政策](https://www.gov.cn/)：**①', '<strong>加粗 <a href="https://www.gov.cn/">政策</a>：</strong>①'),
    ('适用文件是**《财政部公告》（2026年第27号）**，自2026年9月1日起执行。', '<strong>《财政部公告》（2026年第27号）</strong>，'),
    ('参见**“官方解释”**及后文', '<strong>“官方解释”</strong>及'),
    ('满足**（以下条件）**时适用', '<strong>（以下条件）</strong>时'),
])
def test_chinese_bold_with_adjacent_punctuation(source, expected):
    assert expected in render_answer(source)


@pytest.mark.parametrize('source', [
    '`**示例：**①`',
    '```text\n**示例：**①\n```',
    r'\*\*示例：\*\*①',
    '**未闭合：①',
    '**ASCII:**word',
])
def test_literal_stars_are_not_converted_to_bold(source):
    assert '<strong>' not in render_answer(source)


def test_chinese_emphasis_keeps_raw_html_and_unsafe_links_inert():
    html = render_answer('**重要：**①<script>alert(1)</script> [链接](javascript:alert(1))')
    assert '<strong>重要：</strong>' in html
    assert '<script>' not in html
    assert 'href="javascript:' not in html
