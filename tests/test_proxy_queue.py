import threading
import time

from lumia_briefing_room.pipeline.proxy_queue import DIRECT, PREFETCH, PriorityGate, Ticket


def _worker(gate, ticket, order, hold=None):
    def run():
        with gate.slot(ticket):
            order.append(ticket.name)
            if hold:
                hold.wait(5)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def _wait_for(predicate, timeout=3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("조건이 제한 시간 안에 만족되지 않았다")


def test_direct_request_jumps_ahead_of_queued_prefetch():
    gate = PriorityGate()
    order: list[str] = []
    hold = threading.Event()
    running = Ticket("running", PREFETCH)
    _worker(gate, running, order, hold)
    _wait_for(lambda: order == ["running"])

    queued_prefetch = Ticket("prefetch", PREFETCH)
    _worker(gate, queued_prefetch, order)
    _wait_for(lambda: gate.waiting == 1)
    direct = Ticket("direct", DIRECT)
    _worker(gate, direct, order)
    _wait_for(lambda: gate.waiting == 2)

    hold.set()
    _wait_for(lambda: len(order) == 3)
    assert order == ["running", "direct", "prefetch"]


def test_running_prefetch_is_not_interrupted_by_direct_request():
    gate = PriorityGate()
    order: list[str] = []
    hold = threading.Event()
    _worker(gate, Ticket("prefetch", PREFETCH), order, hold)
    _wait_for(lambda: order == ["prefetch"])
    _worker(gate, Ticket("direct", DIRECT), order)
    _wait_for(lambda: gate.waiting == 1)
    time.sleep(0.1)
    assert order == ["prefetch"]
    hold.set()
    _wait_for(lambda: order == ["prefetch", "direct"])


def test_same_priority_is_first_come_first_served():
    gate = PriorityGate()
    order: list[str] = []
    hold = threading.Event()
    _worker(gate, Ticket("first", DIRECT), order, hold)
    _wait_for(lambda: order == ["first"])
    for name in ("b", "c", "d"):
        _worker(gate, Ticket(name, PREFETCH), order)
        _wait_for(lambda n=name: gate.waiting == "bcd".index(n) + 1)
    hold.set()
    _wait_for(lambda: len(order) == 4)
    assert order == ["first", "b", "c", "d"]


def test_promoting_a_queued_prefetch_moves_it_ahead():
    gate = PriorityGate()
    order: list[str] = []
    hold = threading.Event()
    _worker(gate, Ticket("running", DIRECT), order, hold)
    _wait_for(lambda: order == ["running"])
    early = Ticket("early", PREFETCH)
    late = Ticket("late", PREFETCH)
    _worker(gate, early, order)
    _wait_for(lambda: gate.waiting == 1)
    _worker(gate, late, order)
    _wait_for(lambda: gate.waiting == 2)

    gate.promote(late, DIRECT)
    hold.set()
    _wait_for(lambda: len(order) == 3)
    assert order == ["running", "late", "early"]


def test_slot_is_released_when_the_body_raises():
    gate = PriorityGate()
    try:
        with gate.slot(Ticket("boom", DIRECT)):
            raise RuntimeError("x")
    except RuntimeError:
        pass
    order: list[str] = []
    _worker(gate, Ticket("next", DIRECT), order)
    _wait_for(lambda: order == ["next"])
