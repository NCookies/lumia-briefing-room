"""분석 요청 대기열. 스팀 게임 다시 분석·풀영상 만들기·옛 reprocess·영상 파일 분석이 모두 여기를 거친다.

작업은 한 번에 하나씩 요청한 순서대로 돈다(동시 실행은 하지 않는다). 실행 중에 같은 버튼을 또 누르거나 다른 대상의 버튼을 눌러도
거부하지 않고 줄에 세운다. 실시간 감시는 줄에 들어오지 않고 자기 스레드에서 바로 돈다 - 대신 `gate` 가 닫혀 있는 동안(감시가 게임을
처리하는 중, 링버퍼가 원본을 지우기 전에 끝내야 한다) 다음 작업을 시작하지 않는다. 이미 돌고 있는 작업은 멈추지 않는다.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

log = logging.getLogger(__name__)


class AlreadyRunning(Exception):
    """같은 대상이 이미 실행 중이라 다시 줄 세울 수 없다."""


@dataclass
class _Entry:
    key: str
    label: str
    run: Callable[[], None]


class AnalysisQueue:
    def __init__(self, *, gate: Callable[[], bool] = lambda: True, poll_sec: float = 1.0):
        self._gate = gate
        self._poll_sec = poll_sec
        self._cond = threading.Condition()
        self._waiting: list[_Entry] = []
        self._current: _Entry | None = None
        self._thread: threading.Thread | None = None

    def _promote(self) -> None:
        if self._current is None and self._waiting and self._gate():
            self._current = self._waiting.pop(0)
            self._cond.notify_all()

    def _position(self, key: str) -> int | None:
        if self._current is not None and self._current.key == key:
            return 0
        for index, entry in enumerate(self._waiting, start=1):
            if entry.key == key:
                return index
        return None

    def submit(self, key: str, label: str, run: Callable[[], None]) -> int:
        """줄에 세우고 순번을 돌려준다(0 = 지금 실행, N = N번째 대기). 대기 중인 같은 대상은 최신 요청으로 바꾸고 자리는 그대로다."""
        with self._cond:
            if self._current is not None and self._current.key == key:
                raise AlreadyRunning(key)
            entry = _Entry(key, label, run)
            for index, waiting in enumerate(self._waiting):
                if waiting.key == key:
                    self._waiting[index] = entry
                    break
            else:
                self._waiting.append(entry)
            self._promote()
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, daemon=True, name="analysis-queue")
                self._thread.start()
            return self._position(key) or 0

    def position(self, key: str) -> int | None:
        with self._cond:
            return self._position(key)

    def cancel(self, key: str) -> bool:
        """대기 중인 요청만 뺀다. 실행 중인 작업은 건드리지 않는다."""
        with self._cond:
            for index, entry in enumerate(self._waiting):
                if entry.key == key:
                    del self._waiting[index]
                    self._cond.notify_all()
                    return True
            return False

    def snapshot(self) -> list[dict]:
        with self._cond:
            entries = ([self._current] if self._current is not None else []) + self._waiting
            return [{"key": e.key, "label": e.label, "position": i} for i, e in enumerate(entries)]

    def busy(self) -> bool:
        with self._cond:
            return self._current is not None or bool(self._waiting)

    def wait_idle(self, timeout: float) -> bool:
        with self._cond:
            return self._cond.wait_for(lambda: self._current is None and not self._waiting, timeout)

    def _loop(self) -> None:
        while True:
            with self._cond:
                while self._current is None:
                    self._promote()
                    if self._current is None:
                        self._cond.wait(self._poll_sec if self._waiting else None)
                entry = self._current
            try:
                entry.run()
            except Exception:
                log.exception("분석 대기열 작업이 예외로 끝났다: %s", entry.key)
            finally:
                with self._cond:
                    self._current = None
                    self._promote()
                    self._cond.notify_all()
