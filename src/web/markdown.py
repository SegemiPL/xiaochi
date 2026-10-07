"""Safe Markdown with strong emphasis at Chinese punctuation boundaries."""

from __future__ import annotations

import unicodedata

from markdown_it import MarkdownIt
from markdown_it.rules_inline import emphasis
from markdown_it.rules_inline.state_inline import Delimiter, StateInline


def _cjk_or_numbering(character: str) -> bool:
    return any(low <= character <= high for low, high in (
        ('\u2460', '\u24ff'), ('\u2e80', '\u9fff'), ('\uac00', '\ud7af'),
        ('\uf900', '\ufaff'), ('\uff00', '\uffef'),
    ))


def _emphasis(state: StateInline, silent: bool) -> bool:
    """Keep normal delimiter matching, allowing **中文：**① and **13%**计算.

    This runs within the Markdown parser, so escaped stars, code, link targets
    and HTML handling retain their normal rules; raw text is never rewritten.
    """
    if silent or state.src[state.pos] != '*':
        return emphasis.tokenize(state, silent)
    scanned = state.scanDelims(state.pos, True)
    after = state.pos + scanned.length
    cjk_open = (
        scanned.length >= 2 and state.pos > 0 and after < state.posMax
        and _cjk_or_numbering(state.src[state.pos - 1])
        and state.src[after] in '《「『（【“‘'
    )
    cjk_close = (
        scanned.length >= 2 and state.pos > 0 and after < state.posMax
        and unicodedata.category(state.src[state.pos - 1]).startswith('P')
        and _cjk_or_numbering(state.src[after])
    )
    for _ in range(scanned.length):
        token = state.push('text', '', 0)
        token.content = '*'
        state.delimiters.append(Delimiter(
            marker=ord('*'), length=scanned.length, token=len(state.tokens) - 1,
            end=-1, open=scanned.can_open or cjk_open, close=scanned.can_close or cjk_close,
        ))
    state.pos = after
    return True


MARKDOWN = MarkdownIt('gfm-like', {'html': False})
MARKDOWN.inline.ruler.at('emphasis', _emphasis)


def render_answer(text: str) -> str:
    return MARKDOWN.render(text)
