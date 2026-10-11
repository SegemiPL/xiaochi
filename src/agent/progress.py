"""Request-scoped, allowlisted progress; never expose model text or tool arguments."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

STAGES = {
    'preparing': '理解问题',
    'reading': '读取参考材料',
    'thinking': '分析问题',
    'searching': '检索官方政策',
    'reviewing': '核对检索来源',
    'specialist': '分析专项问题',
    'writing': '整理答复',
}
_SINK: ContextVar[Callable[[str], None] | None] = ContextVar('progress_sink', default=None)
_STAGE: ContextVar[str] = ContextVar('progress_stage', default='preparing')


def report_progress(stage: str) -> None:
    if stage not in STAGES:
        return
    _STAGE.set(stage)
    sink = _SINK.get()
    if sink is not None:
        sink(stage)


@contextmanager
def progress_sink(sink: Callable[[str], None] | None) -> Iterator[None]:
    token = _SINK.set(sink)
    stage_token = _STAGE.set('preparing')
    try:
        yield
    finally:
        _STAGE.reset(stage_token)
        _SINK.reset(token)


@contextmanager
def progress_stage(stage: str) -> Iterator[None]:
    previous = _STAGE.get()
    report_progress(stage)
    try:
        yield
    finally:
        report_progress(previous)
