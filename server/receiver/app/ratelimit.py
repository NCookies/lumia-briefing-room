"""IP 별 요청 횟수·실패 횟수 제한. 전부 메모리에만 두고 디스크에 쓰지 않으며 재시작하면 사라진다(docs/privacy.md).

정상 앱은 하루 1회 소량만 보내므로 기본 임계값은 넉넉하다. 창 안에서 요청이 너무 많거나(max_requests),
거부되는 요청(401·404·405·413·422)이 반복되면(max_failures) 그 주소를 block_sec 동안 차단한다.
"""

import time
from collections import deque
from typing import Callable


class RateLimiter:
    def __init__(
        self,
        *,
        window_sec: float,
        max_requests: int,
        max_failures: int,
        block_sec: float,
        clock: Callable[[], float] = time.monotonic,
        on_block: Callable[[str, str], None] | None = None,
        max_tracked: int = 10000,
    ):
        self.window_sec = window_sec
        self.max_requests = max_requests
        self.max_failures = max_failures
        self.block_sec = block_sec
        self.clock = clock
        self.on_block = on_block
        self.max_tracked = max_tracked
        self._hits: dict[str, deque] = {}
        self._fails: dict[str, deque] = {}
        self._blocked: dict[str, float] = {}

    def tracked(self) -> int:
        return len(set(self._hits) | set(self._fails) | set(self._blocked))

    def blocked_count(self) -> int:
        now = self.clock()
        return sum(1 for until in self._blocked.values() if until > now)

    def _trim(self, events: deque, now: float) -> None:
        while events and events[0] <= now - self.window_sec:
            events.popleft()

    def _prune(self, now: float) -> None:
        if self.tracked() < self.max_tracked:
            return
        for table in (self._hits, self._fails):
            for ip in list(table):
                self._trim(table[ip], now)
                if not table[ip]:
                    del table[ip]
        for ip in [ip for ip, until in self._blocked.items() if until <= now]:
            del self._blocked[ip]

    def _block(self, ip: str, reason: str, now: float) -> None:
        self._blocked[ip] = now + self.block_sec
        self._hits.pop(ip, None)
        self._fails.pop(ip, None)
        if self.on_block:
            self.on_block(ip, reason)

    def allow(self, ip: str) -> bool:
        now = self.clock()
        until = self._blocked.get(ip)
        if until is not None:
            if until > now:
                return False
            del self._blocked[ip]
        self._prune(now)
        if self.max_requests <= 0:
            return True
        hits = self._hits.setdefault(ip, deque())
        self._trim(hits, now)
        hits.append(now)
        if len(hits) > self.max_requests:
            self._block(ip, "requests", now)
            return False
        return True

    def record_failure(self, ip: str) -> None:
        if self.max_failures <= 0:
            return
        now = self.clock()
        fails = self._fails.setdefault(ip, deque())
        self._trim(fails, now)
        fails.append(now)
        if len(fails) >= self.max_failures and ip not in self._blocked:
            self._block(ip, "failures", now)
