from datetime import datetime, timezone

from fastapi.testclient import TestClient

from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config
from lumia_briefing_room.pipeline.watch_failures import WatchFailureTracker

UTC = timezone.utc


def test_no_failures_when_watch_has_not_started():
    client = TestClient(create_app(Config()))
    assert client.get("/api/watch/failures").json() == {"failures": []}


def test_lists_a_recorded_failure(tmp_path):
    client = TestClient(create_app(Config()))
    tracker = WatchFailureTracker(tmp_path / "watch_failures.json")
    tracker.record_failure(
        "k1", match_start_utc=datetime(2026, 1, 1, tzinfo=UTC), message="저장 공간 부족", disk_full=True
    )
    client.app.state.watch_failures = tracker

    body = client.get("/api/watch/failures").json()

    assert [f["key"] for f in body["failures"]] == ["k1"]
    assert body["failures"][0]["diskFull"] is True


def test_retry_requests_a_retry_on_the_tracker(tmp_path):
    client = TestClient(create_app(Config()))
    tracker = WatchFailureTracker(tmp_path / "watch_failures.json")
    client.app.state.watch_failures = tracker

    resp = client.post("/api/watch/failures/k1/retry")

    assert resp.status_code == 200 and resp.json() == {"key": "k1", "retrying": True}
    assert tracker.pop_retry_requests() == {"k1"}


def test_retry_without_a_running_watch_is_a_conflict():
    client = TestClient(create_app(Config()))
    resp = client.post("/api/watch/failures/k1/retry")
    assert resp.status_code == 409
