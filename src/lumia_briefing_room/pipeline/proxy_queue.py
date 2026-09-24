import itertools
import threading
from contextlib import contextmanager

DIRECT = 0
PREFETCH = 1


class Ticket:
    """대기열의 한 줄. priority 가 작을수록 먼저, 같으면 먼저 온 순서."""

    def __init__(self, name: str, priority: int) -> None:
        self.name = name
        self.priority = priority
        self.seq = 0


class PriorityGate:
    """한 번에 하나만 통과시키되 대기 중인 것 중 우선순위가 높은 것을 먼저 보낸다. 실행 중인 작업은 끊지 않는다."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._busy = False
        self._waiting: list[Ticket] = []
        self._counter = itertools.count()

    @property
    def waiting(self) -> int:
        with self._cond:
            return len(self._waiting)

    def _is_next(self, ticket: Ticket) -> bool:
        return min(self._waiting, key=lambda t: (t.priority, t.seq)) is ticket

    def promote(self, ticket: Ticket, priority: int) -> None:
        with self._cond:
            if priority < ticket.priority:
                ticket.priority = priority
                self._cond.notify_all()

    @contextmanager
    def slot(self, ticket: Ticket):
        with self._cond:
            ticket.seq = next(self._counter)
            self._waiting.append(ticket)
            while self._busy or not self._is_next(ticket):
                self._cond.wait()
            self._waiting.remove(ticket)
            self._busy = True
        try:
            yield
        finally:
            with self._cond:
                self._busy = False
                self._cond.notify_all()
