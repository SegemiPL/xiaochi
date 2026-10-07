"""Bounded in-memory progress snapshots for the current local server process."""

import threading
import time
from collections import OrderedDict

from src.agent.progress import STAGES
from src.config.product import AGENT_NAME


class ProgressTracker:
    def __init__(self, capacity: int = 128):
        self._lock = threading.Lock()
        self._records: OrderedDict[str, dict] = OrderedDict()
        self._capacity = capacity

    def start(self, request_id: str, conversation_id: str) -> None:
        with self._lock:
            self._records[request_id] = {
                'conversation_id': conversation_id, 'start': time.monotonic(),
                'stage': 'preparing', 'status': 'running',
            }
            self._records.move_to_end(request_id)
            while len(self._records) > self._capacity:
                self._records.popitem(last=False)

    def update(self, request_id: str, stage: str) -> None:
        if stage not in STAGES:
            return
        with self._lock:
            record = self._records.get(request_id)
            if record and record['status'] == 'running':
                record['stage'] = stage

    def finish(self, request_id: str, *, failed: bool = False) -> None:
        with self._lock:
            record = self._records.get(request_id)
            if record:
                record['status'] = 'failed' if failed else 'complete'
                record['end'] = time.monotonic()

    def snapshot(self, request_id: str, conversation_id: str) -> dict:
        with self._lock:
            record = self._records.get(request_id)
            if not record or record['conversation_id'] != conversation_id:
                raise KeyError(request_id)
            status = record['status']
            message = (f'{AGENT_NAME}正在{STAGES[record["stage"]]}……' if status == 'running'
                       else ('答复已完成' if status == 'complete' else '本次查询未完成'))
            return {
                'status': status, 'stage': record['stage'], 'message': message,
                'elapsed_seconds': round(record.get('end', time.monotonic()) - record['start'], 1),
            }
