"""지금 백그라운드에서 하고 있는 일 목록. 화면이 "작업 중" 표시와 자동 갱신을 하는 근거다. (plan-ui.md §0)

스레드 안전하고, 작업이 예외로 끝나도 목록에서 반드시 빠진다.
"""

from __future__ import annotations

import itertools
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager


class ActivityRegistry:
    def __init__(self, clock: Callable[[], float] = time.time):
        self._clock = clock
        self._lock = threading.Lock()
        self._tasks: dict[int, dict] = {}
        self._ids = itertools.count(1)

    def start(self, kind: str, label: str) -> int:
        with self._lock:
            token = next(self._ids)
            self._tasks[token] = {"id": token, "kind": kind, "label": label, "startedAt": self._clock()}
            return token

    def finish(self, token: int) -> None:
        with self._lock:
            self._tasks.pop(token, None)

    @contextmanager
    def track(self, kind: str, label: str) -> Iterator[int]:
        token = self.start(kind, label)
        try:
            yield token
        finally:
            self.finish(token)

    def snapshot(self) -> list[dict]:
        with self._lock:
            return sorted((dict(t) for t in self._tasks.values()), key=lambda t: (t["startedAt"], t["id"]))


registry = ActivityRegistry()
