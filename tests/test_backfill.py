import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from lumia_briefing_room.pipeline import backfill
from lumia_briefing_room.pipeline.backfill_progress import (
    DEFAULT_AVG_GAME_SEC,
    DEFAULT_SCAN_SPEEDUP,
    compute_workload,
    estimate_game_count,
    overall_fraction,
)
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
    def __init__(self, sessions: dict[str, list[GameWindow]], video_seconds: dict[str, float] | None = None):
        self.sessions = sessions
        self.scanned: list[str] = []
        self.video_seconds = video_seconds or {}

    def list_sessions(self):
        return [Path(name) for name in sorted(self.sessions)]

    def session_video_seconds(self, session_dir):
        return self.video_seconds.get(session_dir.name, 0.0)

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

    def __call__(self, session_dir, window, staging, cancel, on_progress=None):
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

    def cancelling(session_dir, window, staging, cancel_event, on_progress=None):
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


def test_scan_progress_is_weighted_by_each_sessions_video_length_not_evenly_by_session_count(tmp_path: Path):
    """B8: 예전에는 세션 개수로 반씩 나눴다(세션이 길든 짧든 균등) — 이제는 실제 영상 길이 비율이어야 한다."""
    scanner = FakeScanner(
        {"bg_a": [], "bg_b": []}, video_seconds={"bg_a": 100.0, "bg_b": 300.0},
    )

    def scan_two_steps(session_dir, cancel, on_progress):
        on_progress(0.5, "")
        on_progress(1.0, "")
        return []

    scanner.scan = scan_two_steps
    reports = []

    _run(tmp_path, scanner, Recorder(), progress=reports.append)

    scan_fractions = [r.fraction for r in reports if r.phase == "scan"]
    total_video = 400.0
    workload = compute_workload(
        video_seconds=total_video, speedup=DEFAULT_SCAN_SPEEDUP,
        game_count=estimate_game_count(total_video), avg_game_sec=DEFAULT_AVG_GAME_SEC,
    )
    expected = [
        overall_fraction(elapsed / DEFAULT_SCAN_SPEEDUP, workload) for elapsed in (50.0, 100.0, 250.0, 400.0)
    ]
    assert scan_fractions == pytest.approx(expected)

    delta_a = scan_fractions[1] - scan_fractions[0]  # bg_a 의 나머지 절반(50초 분량)
    delta_b = scan_fractions[3] - scan_fractions[2]  # bg_b 의 나머지 절반(150초 분량, bg_a 의 3배)
    assert delta_b == pytest.approx(delta_a * 3, rel=0.02)


def test_adaptive_average_updates_after_each_game_and_is_used_for_the_next_ones_progress(
    tmp_path: Path, monkeypatch
):
    """§7 확인 필요 1번: 게임당 평균 처리 시간을 이번 실행에서 실제로 걸린 시간으로 보정한다."""
    scanner = FakeScanner({"bg_1049590_20260923_095917": [_win(1, 0), _win(2, 30)]})
    process = Recorder()

    # 첫 게임 처리에 200초가 걸린 것처럼(기본 상수 80초보다 훨씬 길게) 흉내낸다.
    times = iter([0.0, 200.0, 200.0, 400.0])
    monkeypatch.setattr(backfill.time, "monotonic", lambda: next(times))

    reports = []
    _run(tmp_path, scanner, process, progress=reports.append)

    process_reports = [r for r in reports if r.phase == "process"]
    game2_start = next(r for r in process_reports if r.games_done == 1 and r.fraction < 1.0)

    # 둘째 게임 시작 시점엔 이동 평균이 200초로 보정돼 있어야 한다(영상 길이 0 이라 스캔 작업량도 0,
    # 분석 작업량 = 게임 2개 × 200초 = 400, 이미 게임 1개 분량 200초를 썼으니 정확히 절반).
    assert game2_start.fraction == pytest.approx(0.5)


def test_game_internal_progress_moves_the_bar_during_a_single_game(tmp_path: Path):
    """B8 (3): 게임 하나(60~100초)를 처리하는 동안에도 진행률이 여러 지점에서 움직여야 한다."""
    scanner = FakeScanner({"bg_1049590_20260923_095917": [_win(1, 0)]})
    base = Recorder()

    def process(session_dir, window, staging, cancel, on_progress=None):
        if on_progress is not None:
            on_progress(0.0)
            on_progress(0.5)
        return base(session_dir, window, staging, cancel, on_progress)

    reports = []
    _run(tmp_path, scanner, process, progress=reports.append)

    process_fractions = [r.fraction for r in reports if r.phase == "process"]
    assert len(process_fractions) >= 3
    assert process_fractions == sorted(process_fractions)
    assert process_fractions[0] < process_fractions[-1]


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


def _game_json(games: Path, key: str, start: str, *, video: bool, deleted: bool = False) -> None:
    folder = games / key
    folder.mkdir(parents=True)
    data = {"gameKey": key, "matchStartUtc": start, "fullVideo": {"path": "full.mp4"} if video else None}
    if deleted:
        data["fullVideoDeletedAt"] = "2026-09-29T00:00:00Z"
    (folder / "game.json").write_text(json.dumps(data), encoding="utf-8")
    if video:
        (folder / "full.mp4").write_bytes(b"v")


def test_known_starts_with_games_dir_count_only_games_that_have_or_had_a_full_video(tmp_path: Path):
    clips, games = tmp_path / "clips", tmp_path / "games"
    (clips / ".trash").mkdir(parents=True)
    _game_json(games, "20260923_100000", "2026-09-23T10:00:00Z", video=True)
    _game_json(games, "20260923_110000", "2026-09-23T11:00:00Z", video=False)  # 이전 버전 게임 - 풀영상을 새로 만든다
    _game_json(games, "20260923_120000", "2026-09-23T12:00:00Z", video=False, deleted=True)  # 자동 정리로 지운 것
    (clips / "a.json").write_text(json.dumps({"matchStartUtc": "2026-09-23T11:00:00Z"}), encoding="utf-8")
    (clips / ".trash" / "t.json").write_text(json.dumps({"matchStartUtc": "2026-09-23T13:00:00Z"}), encoding="utf-8")

    starts = backfill.collect_known_starts(clips, games)

    assert sorted(s.hour for s in starts) == [10, 12, 13]


def test_known_starts_without_games_dir_keep_the_old_behaviour(tmp_path: Path):
    clips = tmp_path / "clips"
    clips.mkdir()
    (clips / "a.json").write_text(json.dumps({"matchStartUtc": "2026-09-23T10:00:00Z"}), encoding="utf-8")

    assert len(backfill.collect_known_starts(clips)) == 1
