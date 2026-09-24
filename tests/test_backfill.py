import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from lumia_briefing_room.pipeline import backfill
from lumia_briefing_room.pipeline.session_scan import GameWindow, ScanCancelled

BASE = datetime(2026, 9, 23, 10, 0, 0, tzinfo=timezone.utc)


def _win(index: int, start_min: float, length_min: float = 10, *, cut=False, running=False) -> GameWindow:
    start = BASE + timedelta(minutes=start_min)
    end = start + timedelta(minutes=length_min)
    return GameWindow(
        index=index, hud_start_utc=start, hud_end_utc=end, end_utc=end + timedelta(minutes=2),
        confidence=1.0, cut_at_start=cut, still_running=running,
    )


class FakeScanner:
    def __init__(self, sessions: dict[str, list[GameWindow]]):
        self.sessions = sessions
        self.scanned: list[str] = []

    def list_sessions(self):
        return [Path(name) for name in sorted(self.sessions)]

    def scan(self, session_dir, cancel, on_progress):
        self.scanned.append(session_dir.name)
        on_progress(1.0, "")
        return self.sessions[session_dir.name]


class Recorder:
    """경기 하나를 처리하는 척하고 스테이징 폴더에 클립 파일을 만든다."""

    def __init__(self, fail_on: set[str] | None = None, cancel_after: int | None = None, cancel=None):
        self.calls: list[tuple[str, datetime]] = []
        self.fail_on = fail_on or set()
        self.cancel_after = cancel_after
        self.cancel = cancel

    def __call__(self, session_dir, window, staging, cancel):
        start = window.hud_start_utc
        self.calls.append((session_dir.name, start))
        if start.isoformat() in self.fail_on:
            raise RuntimeError("처리 실패")
        clip_id = f"{start:%Y%m%d_%H%M%S}_01"
        (staging / ".thumbs").mkdir(parents=True, exist_ok=True)
        (staging / f"{clip_id}.mp4").write_bytes(b"video")
        (staging / ".thumbs" / f"{clip_id}.jpg").write_bytes(b"thumb")
        meta = {"matchStartUtc": start.isoformat(), "thumbnailPath": f".thumbs/{clip_id}.jpg"}
        (staging / f"{clip_id}.json").write_text(json.dumps(meta), encoding="utf-8")
        if self.cancel_after is not None and len(self.calls) >= self.cancel_after:
            self.cancel.set()
        return [staging / f"{clip_id}.json"]


def _run(tmp_path, scanner, process, *, known=None, cancel=None, progress=None):
    return backfill.run_backfill(
        scanner=scanner,
        process_window=process,
        clips_dir=tmp_path / "clips",
        state_dir=tmp_path / "state",
        staging_root=tmp_path / "staging",
        known_starts=known or [],
        cancel=cancel,
        on_progress=progress,
    )


def test_games_are_processed_oldest_first_across_sessions(tmp_path: Path):
    scanner = FakeScanner({
        "bg_1049590_20260924_060228": [_win(1, 1440)],
        "bg_1049590_20260923_095917": [_win(1, 0), _win(2, 30)],
    })
    process = Recorder()

    result = _run(tmp_path, scanner, process)

    assert [c[1] for c in process.calls] == sorted(c[1] for c in process.calls)
    assert [c[0] for c in process.calls] == [
        "bg_1049590_20260923_095917", "bg_1049590_20260923_095917", "bg_1049590_20260924_060228",
    ]
    assert result.games_processed == 3 and result.clips_created == 3
    assert result.cancelled is False


def test_clips_are_moved_into_the_real_folder_json_last(tmp_path: Path):
    scanner = FakeScanner({"bg_1049590_20260923_095917": [_win(1, 0)]})

    _run(tmp_path, scanner, Recorder())

    clips = tmp_path / "clips"
    names = sorted(p.name for p in clips.iterdir())
    assert any(n.endswith(".mp4") for n in names) and any(n.endswith(".json") for n in names)
    assert len(list((clips / ".thumbs").iterdir())) == 1
    assert not list((tmp_path / "staging").glob("*/*")), "스테이징이 비워져야 한다"


def test_commit_moves_the_json_after_the_video_and_thumbnail(tmp_path: Path, monkeypatch):
    staging, clips = tmp_path / "s", tmp_path / "c"
    (staging / ".thumbs").mkdir(parents=True)
    (staging / "a.mp4").write_bytes(b"v")
    (staging / "a.json").write_text("{}", encoding="utf-8")
    (staging / ".thumbs" / "a.jpg").write_bytes(b"t")
    order = []
    real_move = backfill.shutil.move
    monkeypatch.setattr(backfill.shutil, "move", lambda src, dst: (order.append(Path(src).name), real_move(src, dst))[1])

    backfill.commit_staging(staging, clips)

    assert order.index("a.json") == len(order) - 1


def test_known_games_are_skipped(tmp_path: Path):
    scanner = FakeScanner({"bg_1049590_20260923_095917": [_win(1, 0), _win(2, 30)]})
    process = Recorder()
    known = [BASE + timedelta(minutes=30) - timedelta(seconds=25)]

    result = _run(tmp_path, scanner, process, known=known)

    assert len(process.calls) == 1
    assert result.skipped["known"] == 1


def test_a_known_start_far_from_any_game_does_not_hide_it(tmp_path: Path):
    scanner = FakeScanner({"bg_1049590_20260923_095917": [_win(1, 0)]})
    process = Recorder()

    _run(tmp_path, scanner, process, known=[BASE + timedelta(hours=5)])

    assert len(process.calls) == 1


def test_games_cut_at_the_start_or_still_running_are_skipped_and_counted(tmp_path: Path):
    scanner = FakeScanner({"bg_1049590_20260923_095917": [
        _win(1, 0, cut=True), _win(2, 30), _win(3, 60, running=True),
    ]})
    process = Recorder()

    result = _run(tmp_path, scanner, process)

    assert len(process.calls) == 1
    assert result.skipped["cut_at_start"] == 1 and result.skipped["still_running"] == 1


def test_a_second_run_skips_what_is_already_done(tmp_path: Path):
    scanner = FakeScanner({"bg_1049590_20260923_095917": [_win(1, 0), _win(2, 30)]})
    first = Recorder()
    _run(tmp_path, scanner, first)

    second = Recorder()
    result = _run(tmp_path, scanner, second)

    assert second.calls == []
    assert result.skipped["already_done"] == 2


def test_a_failing_game_does_not_stop_the_others_and_is_retried_next_time(tmp_path: Path):
    scanner = FakeScanner({"bg_1049590_20260923_095917": [_win(1, 0), _win(2, 30)]})
    bad = (BASE + timedelta(minutes=0)).isoformat()
    first = Recorder(fail_on={bad})

    result = _run(tmp_path, scanner, first)

    assert result.games_processed == 1 and result.games_failed == 1
    assert not list((tmp_path / "staging").glob("*/*")), "실패한 경기의 스테이징도 치워야 한다"

    retry = Recorder()
    _run(tmp_path, scanner, retry)
    assert [c[1].isoformat() for c in retry.calls] == [bad]


def test_a_game_that_keeps_failing_is_given_up_after_three_tries(tmp_path: Path):
    scanner = FakeScanner({"bg_1049590_20260923_095917": [_win(1, 0)]})
    bad = (BASE).isoformat()

    for _ in range(3):
        _run(tmp_path, scanner, Recorder(fail_on={bad}))
    fourth = Recorder(fail_on={bad})
    result = _run(tmp_path, scanner, fourth)

    assert fourth.calls == []
    assert result.skipped["gave_up"] == 1


def test_cancel_between_games_keeps_finished_ones_and_resumes_later(tmp_path: Path):
    scanner = FakeScanner({"bg_1049590_20260923_095917": [_win(1, 0), _win(2, 30), _win(3, 60)]})
    cancel = threading.Event()
    first = Recorder(cancel_after=1, cancel=cancel)

    result = _run(tmp_path, scanner, first, cancel=cancel)

    assert result.cancelled is True
    assert len(first.calls) == 1
    assert len(list((tmp_path / "clips").glob("*.json"))) == 1

    second = Recorder()
    resumed = _run(tmp_path, scanner, second)

    assert len(second.calls) == 2
    assert resumed.skipped["already_done"] == 1
    assert len(list((tmp_path / "clips").glob("*.json"))) == 3


def test_cancel_in_the_middle_of_a_game_leaves_no_partial_clip(tmp_path: Path):
    scanner = FakeScanner({"bg_1049590_20260923_095917": [_win(1, 0), _win(2, 30)]})
    cancel = threading.Event()

    def cancelling(session_dir, window, staging, cancel_event):
        (staging / "half.mp4").write_bytes(b"partial")
        cancel.set()
        raise backfill.GameCancelled()

    result = _run(tmp_path, scanner, cancelling, cancel=cancel)

    assert result.cancelled is True
    assert list((tmp_path / "clips").glob("*")) == []
    assert not list((tmp_path / "staging").glob("*/*"))


def test_cancel_while_scanning_stops_before_any_processing(tmp_path: Path):
    class CancellingScanner(FakeScanner):
        def scan(self, session_dir, cancel, on_progress):
            raise ScanCancelled()

    scanner = CancellingScanner({"bg_1049590_20260923_095917": []})
    process = Recorder()

    result = _run(tmp_path, scanner, process)

    assert result.cancelled is True and process.calls == []


def test_leftover_staging_from_a_crash_is_cleaned_at_start(tmp_path: Path):
    stale = tmp_path / "staging" / "scan_old_game"
    stale.mkdir(parents=True)
    (stale / "half.mp4").write_bytes(b"partial")
    scanner = FakeScanner({"bg_1049590_20260923_095917": []})

    _run(tmp_path, scanner, Recorder())

    assert not stale.exists()


def test_progress_covers_scan_and_processing_and_ends_at_one(tmp_path: Path):
    scanner = FakeScanner({"bg_1049590_20260923_095917": [_win(1, 0), _win(2, 30)]})
    reports = []

    _run(tmp_path, scanner, Recorder(), progress=reports.append)

    fractions = [r.fraction for r in reports]
    assert fractions == sorted(fractions)
    assert fractions[-1] == pytest.approx(1.0)
    assert {r.phase for r in reports} >= {"scan", "process", "done"}
    assert reports[-1].games_done == 2 and reports[-1].games_total == 2


def test_collect_known_starts_reads_clips_trash_and_game_records(tmp_path: Path):
    clips = tmp_path / "clips"
    (clips / ".trash").mkdir(parents=True)
    (clips / ".games").mkdir()
    (clips / "a.json").write_text(json.dumps({"matchStartUtc": "2026-09-23T10:00:00+00:00"}), encoding="utf-8")
    (clips / ".trash" / "b.json").write_text(json.dumps({"matchStartUtc": "2026-09-23T11:00:00Z"}), encoding="utf-8")
    (clips / ".games" / "c.json").write_text(json.dumps({"matchStartUtc": "2026-09-23T12:00:00.500000Z"}), encoding="utf-8")
    (clips / "broken.json").write_text("not json", encoding="utf-8")
    (clips / "nostart.json").write_text("{}", encoding="utf-8")

    starts = backfill.collect_known_starts(clips)

    assert sorted(s.hour for s in starts) == [10, 11, 12]
    assert all(s.tzinfo is not None for s in starts)


def test_overlap_uses_a_tolerance_before_the_hud_start():
    window = _win(1, 0)
    log_start = window.hud_start_utc - timedelta(seconds=45)

    assert backfill.overlaps_known(window, [log_start]) is True
    assert backfill.overlaps_known(window, [window.hud_start_utc - timedelta(minutes=10)]) is False
    assert backfill.overlaps_known(window, [window.end_utc + timedelta(seconds=1)]) is False
    assert backfill.overlaps_known(window, []) is False
