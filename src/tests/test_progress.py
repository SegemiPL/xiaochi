"""Progress scope isolation and bounded public snapshots."""

import pytest
from src.agent.progress import progress_sink, progress_stage, report_progress
from src.web.progress import ProgressTracker


def test_progress_scope_restores_nested_stage_and_does_not_cross_requests():
    first, second = [], []
    with progress_sink(first.append):
        report_progress('searching')
        with progress_stage('reviewing'):
            report_progress('PRIVATE_TEXT')
    report_progress('writing')
    with progress_sink(second.append):
        report_progress('thinking')
    assert first == ['searching', 'reviewing', 'searching']
    assert second == ['thinking']


def test_progress_tracker_evicts_old_snapshots_and_freezes_finished_status():
    tracker = ProgressTracker(capacity=1)
    tracker.start('old', 'one')
    tracker.start('new', 'two')
    with pytest.raises(KeyError):
        tracker.snapshot('old', 'one')
    tracker.update('new', 'searching')
    tracker.finish('new', failed=True)
    before = tracker.snapshot('new', 'two')
    tracker.update('new', 'writing')
    assert tracker.snapshot('new', 'two') == before
    assert before['status'] == 'failed'
    assert 'query' not in before and 'tool' not in before
