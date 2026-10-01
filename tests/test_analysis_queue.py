import threading

import pytest

from lumia_briefing_room.api.analysis_queue import AlreadyRunning, AnalysisQueue


class Gate:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def run(self, log, name):
        def run():
            log.append(f"start {name}")
            self.started.set()
            assert self.release.wait(2)
            log.append(f"end {name}")

        return run


def make(**kw):
    return AnalysisQueue(poll_sec=0.01, **kw)


def test_tasks_run_one_at_a_time_in_request_order():
    queue, log = make(), []
    first = Gate()
    assert queue.submit("a", "A", first.run(log, "a")) == 0
    assert first.started.wait(2)
    assert queue.submit("b", "B", lambda: log.append("b")) == 1
    assert queue.submit("c", "C", lambda: log.append("c")) == 2
    assert queue.position("a") == 0 and queue.position("b") == 1 and queue.position("c") == 2
    assert log == ["start a"], "앞 작업이 끝나기 전에는 다음이 시작하지 않는다"
    first.release.set()
    assert queue.wait_idle(2)
    assert log == ["start a", "end a", "b", "c"]
    assert queue.position("a") is None and not queue.busy()


def test_a_waiting_request_is_replaced_by_the_latest_one_and_keeps_its_place():
    queue, log = make(), []
    first = Gate()
    queue.submit("a", "A", first.run(log, "a"))
    first.started.wait(2)
    queue.submit("b", "B", lambda: log.append("b-old"))
    queue.submit("c", "C", lambda: log.append("c"))
    assert queue.submit("b", "B2", lambda: log.append("b-new")) == 1
    assert [e["label"] for e in queue.snapshot()] == ["A", "B2", "C"]
    first.release.set()
    queue.wait_idle(2)
    assert log == ["start a", "end a", "b-new", "c"]


def test_the_same_target_cannot_be_queued_again_while_it_is_running():
    queue = make()
    first = Gate()
    queue.submit("a", "A", first.run([], "a"))
    first.started.wait(2)
    with pytest.raises(AlreadyRunning):
        queue.submit("a", "A", lambda: None)
    first.release.set()
    queue.wait_idle(2)


def test_a_waiting_task_can_be_cancelled_but_the_running_one_cannot():
    queue, log = make(), []
    first = Gate()
    queue.submit("a", "A", first.run(log, "a"))
    first.started.wait(2)
    queue.submit("b", "B", lambda: log.append("b"))
    queue.submit("c", "C", lambda: log.append("c"))
    assert queue.cancel("b") is True
    assert queue.cancel("a") is False and queue.cancel("nope") is False
    assert queue.position("c") == 1
    first.release.set()
    queue.wait_idle(2)
    assert log == ["start a", "end a", "c"]


def test_a_failing_task_does_not_stop_the_queue():
    queue, log = make(), []

    def boom():
        raise RuntimeError("x")

    queue.submit("a", "A", boom)
    queue.submit("b", "B", lambda: log.append("b"))
    assert queue.wait_idle(2)
    assert log == ["b"]


def test_the_next_task_waits_while_the_gate_is_closed():
    """실시간 감시가 게임을 처리하는 동안(링버퍼) 새 분석을 시작하지 않는다."""
    open_ = threading.Event()
    queue, log = make(gate=open_.is_set), []
    queue.submit("a", "A", lambda: log.append("a"))
    assert not queue.wait_idle(0.15)
    assert log == [] and queue.position("a") == 1, "아직 시작하지 않았으니 대기 1번"
    open_.set()
    assert queue.wait_idle(2)
    assert log == ["a"]
