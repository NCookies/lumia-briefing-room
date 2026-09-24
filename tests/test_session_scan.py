import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.pipeline import session_scan as scan
from lumia_briefing_room.pipeline.vod_store import StateCache

START = datetime(2026, 9, 23, 9, 59, 17, tzinfo=timezone.utc)
SEG = 3.0


def _state(t: float, *, ingame: bool, day: int | None = 1) -> FrameState:
    return FrameState(
        t=t, combat=None, face_value=None, face_sat=None, k=None, a=None,
        day_night="day" if ingame else None, game_day=day if ingame else None,
    )


def _timeline(*spans: tuple[float, float], end: float, step: float = SEG) -> list[FrameState]:
    """인게임 구간(시작, 끝 초)을 주면 그 밖은 로비로 채운 프레임열."""
    states = []
    t = 0.0
    while t <= end:
        states.append(_state(t, ingame=any(a <= t <= b for a, b in spans)))
        t += step
    return states


def _utc(sec: float) -> datetime:
    return START + timedelta(seconds=sec)


def test_two_games_become_two_windows_with_utc_bounds():
    states = _timeline((300, 900), (1200, 2400), end=3000)

    windows = scan.windows_from_states(states, session_start_utc=START, seg_sec=SEG, post_game_sec=60)

    assert len(windows) == 2
    assert windows[0].hud_start_utc == _utc(300) and windows[0].hud_end_utc == _utc(900)
    assert windows[1].hud_start_utc == _utc(1200)


def test_end_gets_a_margin_for_the_result_screen_but_not_past_the_next_game():
    states = _timeline((300, 900), (1002, 2400), end=3000)

    windows = scan.windows_from_states(states, session_start_utc=START, seg_sec=SEG, post_game_sec=300)

    assert len(windows) == 2
    assert windows[0].end_utc == _utc(1002)
    assert windows[1].end_utc == _utc(2400 + 300)


def test_margin_is_capped_at_the_end_of_the_recording():
    states = _timeline((300, 900), end=960)

    windows = scan.windows_from_states(states, session_start_utc=START, seg_sec=SEG, post_game_sec=300)

    assert windows[0].end_utc == _utc(960 + SEG)


def test_a_game_that_reaches_the_first_segment_is_marked_as_cut_at_the_start():
    """링버퍼가 경기 앞부분을 지웠다 — 시작을 알 수 없다."""
    states = _timeline((0, 600), (900, 1500), end=1800)

    windows = scan.windows_from_states(states, session_start_utc=START, seg_sec=SEG, post_game_sec=60)

    assert windows[0].cut_at_start is True
    assert windows[1].cut_at_start is False


def test_a_game_that_reaches_the_last_segment_is_marked_as_still_running():
    states = _timeline((300, 900), (1200, 1800), end=1800)

    windows = scan.windows_from_states(states, session_start_utc=START, seg_sec=SEG, post_game_sec=60)

    assert windows[0].still_running is False
    assert windows[1].still_running is True


def test_short_blips_are_not_games():
    states = _timeline((300, 330), end=900)
    assert scan.windows_from_states(states, session_start_utc=START, seg_sec=SEG, post_game_sec=60) == []


def test_empty_input_gives_no_windows():
    assert scan.windows_from_states([], session_start_utc=START, seg_sec=SEG, post_game_sec=60) == []


def test_window_key_is_stable_and_uses_the_session_and_hud_start():
    states = _timeline((300, 900), end=1200)
    w = scan.windows_from_states(states, session_start_utc=START, seg_sec=SEG, post_game_sec=60)[0]

    assert scan.window_key("bg_1049590_20260923_095917", w) == scan.window_key("bg_1049590_20260923_095917", w)
    assert scan.window_key("bg_1049590_20260923_095917", w) != scan.window_key("bg_1049590_20260924_060228", w)


def test_session_dirs_are_eternal_return_only_and_oldest_first(tmp_path: Path):
    for name in [
        "bg_1049590_20260924_060228", "bg_5075020_20260904_061655", "bg_1049590_20260923_095917",
        "not_a_session", "bg_1049590_20260901_100000",
    ]:
        (tmp_path / name).mkdir()
    (tmp_path / "bg_1049590_20260910_100000").write_text("file, not folder", encoding="utf-8")

    found = scan.list_session_dirs(tmp_path)

    assert [p.name for p in found] == [
        "bg_1049590_20260901_100000", "bg_1049590_20260923_095917", "bg_1049590_20260924_060228",
    ]


def test_session_dirs_of_a_missing_root_is_empty(tmp_path: Path):
    assert scan.list_session_dirs(tmp_path / "nope") == []


class FakeSource:
    """세그먼트 번호 범위를 (시각, 프레임) 로 내주는 가짜. 실제 ffmpeg 없이 스캔 흐름을 시험한다."""

    def __init__(self, first: int, last: int, seg_sec: float = SEG):
        self.first, self.last, self.seg = first, last, seg_sec
        self.width, self.height = 8, 6
        self.started_at = None

    def gaps(self):
        return []

    def frames(self):
        for n in range(self.first, self.last + 1):
            yield (n - 1) * self.seg, np.zeros((6, 8, 3), dtype=np.uint8)


def _reader(ingame_ranges):
    def read(frame, t):
        return _state(t, ingame=any(a <= t <= b for a, b in ingame_ranges))

    return read


def _scan(tmp_path, ingame, *, first=1, last=400, cancel=None, existing=None, reader=None, progress=None):
    cache = StateCache(tmp_path / "s.states.jsonl.gz")
    made = []

    def factory(first_segment):
        made.append(first_segment)
        return FakeSource(first_segment, last)

    states = scan.scan_frames(
        cache,
        segment_numbers=existing or list(range(first, last + 1)),
        seg_sec=SEG,
        source_factory=factory,
        read_frame=reader or _reader(ingame),
        cancel=cancel,
        on_progress=progress,
    )
    return states, made, cache


def test_scan_reads_every_segment_and_caches_the_states(tmp_path: Path):
    states, made, cache = _scan(tmp_path, [(300, 900)], last=400)

    assert len(states) == 400
    assert made == [1]
    assert len(cache.load()) == 400


def test_scan_resumes_after_the_last_cached_segment(tmp_path: Path):
    cache = StateCache(tmp_path / "s.states.jsonl.gz")
    cache.append([_state((n - 1) * SEG, ingame=False) for n in range(1, 101)])

    states, made, _ = _scan(tmp_path, [], last=400)

    assert made == [101]
    assert len(states) == 400


def test_scan_stops_on_cancel_but_keeps_what_it_read(tmp_path: Path):
    cancel = threading.Event()
    seen = []

    def reader(frame, t):
        seen.append(t)
        if len(seen) == 150:
            cancel.set()
        return _state(t, ingame=False)

    with pytest.raises(scan.ScanCancelled):
        _scan(tmp_path, [], last=400, cancel=cancel, reader=reader)

    cached = StateCache(tmp_path / "s.states.jsonl.gz").load()
    assert 150 <= len(cached) < 400

    states, made, _ = _scan(tmp_path, [], last=400)
    assert made == [len(cached) + 1]
    assert len(states) == 400


def test_scan_skips_segments_the_ring_buffer_already_deleted(tmp_path: Path):
    states, made, _ = _scan(tmp_path, [], first=1, last=400, existing=list(range(201, 401)))
    assert made == [201]


def test_scan_reports_progress_as_a_fraction(tmp_path: Path):
    reports = []
    _scan(tmp_path, [], last=400, progress=lambda fraction, message: reports.append(fraction))

    assert reports and reports[-1] == pytest.approx(1.0)
    assert all(0.0 <= r <= 1.0 for r in reports)
    assert reports == sorted(reports)


def test_scan_of_nothing_returns_nothing(tmp_path: Path):
    cache = StateCache(tmp_path / "s.states.jsonl.gz")
    states = scan.scan_frames(
        cache, segment_numbers=[], seg_sec=SEG, source_factory=lambda n: FakeSource(n, n),
        read_frame=_reader([]),
    )
    assert states == []
