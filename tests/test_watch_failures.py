from datetime import datetime, timezone

from lumia_briefing_room.pipeline.watch_failures import WatchFailureTracker

UTC = timezone.utc


def test_record_failure_is_visible_in_list(tmp_path):
    tracker = WatchFailureTracker(tmp_path / "watch_failures.json")
    tracker.record_failure(
        "k1", match_start_utc=datetime(2026, 1, 1, tzinfo=UTC), message="저장 공간 부족", disk_full=True
    )

    [entry] = tracker.list()
    assert entry["key"] == "k1" and entry["diskFull"] is True and entry["message"] == "저장 공간 부족"


def test_record_success_clears_the_failure(tmp_path):
    tracker = WatchFailureTracker(tmp_path / "watch_failures.json")
    tracker.record_failure(
        "k1", match_start_utc=datetime(2026, 1, 1, tzinfo=UTC), message="실패", disk_full=False
    )

    tracker.record_success("k1")

    assert tracker.list() == []


def test_state_survives_reload_from_the_same_path(tmp_path):
    path = tmp_path / "watch_failures.json"
    tracker = WatchFailureTracker(path)
    tracker.record_failure(
        "k1", match_start_utc=datetime(2026, 1, 1, tzinfo=UTC), message="실패", disk_full=False
    )

    reloaded = WatchFailureTracker(path)

    assert [e["key"] for e in reloaded.list()] == ["k1"]


def test_missing_file_starts_empty(tmp_path):
    tracker = WatchFailureTracker(tmp_path / "does_not_exist.json")
    assert tracker.list() == []


def test_retry_requests_are_returned_once_and_then_cleared(tmp_path):
    tracker = WatchFailureTracker(tmp_path / "watch_failures.json")
    tracker.request_retry("k1")

    assert tracker.pop_retry_requests() == {"k1"}
    assert tracker.pop_retry_requests() == set()


def test_list_is_ordered_oldest_failure_first(tmp_path):
    tracker = WatchFailureTracker(tmp_path / "watch_failures.json")
    tracker.record_failure("k2", match_start_utc=datetime(2026, 1, 2, tzinfo=UTC), message="", disk_full=False)
    tracker.record_failure("k1", match_start_utc=datetime(2026, 1, 1, tzinfo=UTC), message="", disk_full=False)

    assert [e["key"] for e in tracker.list()] == ["k2", "k1"]
