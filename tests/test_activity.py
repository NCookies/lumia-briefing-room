import threading
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.activity import ActivityRegistry, registry
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config

from test_watcher import UTC, _make_session_dir, _match, _polling


def test_tasks_appear_while_running_and_disappear_when_finished():
    reg = ActivityRegistry(clock=lambda: 100.0)
    with reg.track("watch", "게임 분석 중"):
        tasks = reg.snapshot()
        assert [(t["kind"], t["label"], t["startedAt"]) for t in tasks] == [("watch", "게임 분석 중", 100.0)]
    assert reg.snapshot() == []


def test_a_failing_task_is_still_removed():
    reg = ActivityRegistry()
    with pytest.raises(RuntimeError):
        with reg.track("watch", "x"):
            raise RuntimeError("실패")
    assert reg.snapshot() == []


def test_concurrent_tasks_are_listed_oldest_first():
    ticks = iter([1.0, 2.0])
    reg = ActivityRegistry(clock=lambda: next(ticks))
    first, second = reg.start("a", "첫째"), reg.start("b", "둘째")
    assert [t["label"] for t in reg.snapshot()] == ["첫째", "둘째"]
    reg.finish(first)
    assert [t["label"] for t in reg.snapshot()] == ["둘째"]
    reg.finish(second)
    reg.finish(second)
    assert reg.snapshot() == []


def test_snapshot_is_safe_across_threads():
    reg = ActivityRegistry()

    def work():
        for _ in range(200):
            with reg.track("t", "x"):
                reg.snapshot()

    threads = [threading.Thread(target=work) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert reg.snapshot() == []


def test_the_watcher_reports_a_game_being_processed(tmp_path):
    _make_session_dir(tmp_path, 1049590, datetime(2026, 9, 19, 12, 0, tzinfo=UTC))
    seen = []

    def process(session_dir, match, rescue):
        seen.append(registry.snapshot())

    _polling(
        tmp_path, lambda: [_match(5, 25)], process=process,
        now=lambda: datetime(2026, 9, 19, 13, 30, tzinfo=UTC), stops=2,
    )

    assert len(seen) == 1 and [t["kind"] for t in seen[0]] == ["watch"]
    assert "게임" in seen[0][0]["label"]
    assert registry.snapshot() == []


def test_the_watcher_clears_the_task_even_when_processing_fails(tmp_path):
    _make_session_dir(tmp_path, 1049590, datetime(2026, 9, 19, 12, 0, tzinfo=UTC))

    def process(session_dir, match, rescue):
        raise RuntimeError("분석 실패")

    _polling(
        tmp_path, lambda: [_match(5, 25)], process=process,
        now=lambda: datetime(2026, 9, 19, 13, 30, tzinfo=UTC), stops=2, failures=1,
    )
    assert registry.snapshot() == []


def test_activity_endpoint_lists_running_tasks():
    client = TestClient(create_app(Config()))
    assert client.get("/api/activity").json() == {"tasks": []}
    with registry.track("watch", "게임 분석 중 (9/24 15:55)"):
        body = client.get("/api/activity").json()
    assert [t["label"] for t in body["tasks"]] == ["게임 분석 중 (9/24 15:55)"]
