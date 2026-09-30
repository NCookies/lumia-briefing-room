import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from lumia_briefing_room.config import Config, PathsConfig
from lumia_briefing_room.detect.match import DetectionCancelled
from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.pipeline import backfill_runtime as rt
from lumia_briefing_room.pipeline.backfill import GameCancelled
from lumia_briefing_room.pipeline.clip import ClipCutError
from lumia_briefing_room.pipeline.session_scan import GameWindow

START = datetime(2026, 9, 23, 10, 0, 0, tzinfo=timezone.utc)


def _window(minutes: float = 12) -> GameWindow:
    hud_end = START + timedelta(minutes=minutes)
    return GameWindow(
        index=1, hud_start_utc=START, hud_end_utc=hud_end, end_utc=hud_end + timedelta(minutes=2),
        confidence=1.0, cut_at_start=False, still_running=False,
    )


def test_staging_config_never_writes_thumbnails_outside_the_staging_folder(tmp_path: Path):
    cfg = Config(paths=PathsConfig(clips=tmp_path / "real", thumbnails=tmp_path / "elsewhere"))

    staged = rt.staging_config(cfg)

    assert staged.paths.thumbnails is None
    assert cfg.paths.thumbnails == tmp_path / "elsewhere", "원본 설정은 건드리지 않는다"


def test_states_from_deleted_segments_are_dropped():
    """캐시에는 링버퍼가 이미 지운 구간의 판독이 남아 있을 수 있다 — 살아 있는 세그먼트만 경계 계산에 쓴다."""
    def st(t):
        return FrameState(t=t, combat=None, face_value=None, face_sat=None, k=None, a=None, day_night="day")

    states = [st(0.0), st(3.0), st(6.0), st(9.0), st(12.0)]

    kept = rt.alive_states(states, first_segment=3, seg_sec=3.0)

    assert [s.t for s in kept] == [6.0, 9.0, 12.0]


def test_alive_states_keeps_everything_when_nothing_was_deleted():
    def st(t):
        return FrameState(t=t, combat=None, face_value=None, face_sat=None, k=None, a=None, day_night=None)

    assert len(rt.alive_states([st(0.0), st(3.0)], first_segment=1, seg_sec=3.0)) == 2


def _process(monkeypatch, behavior):
    calls = {}

    def fake_process_match(session, start, end, cfg, **kwargs):
        calls.update(session=session, start=start, end=end, cfg=cfg, **kwargs)
        return behavior()

    monkeypatch.setattr(rt, "process_match", fake_process_match)
    monkeypatch.setattr(rt.RecordingSession, "load", classmethod(lambda cls, d: f"session:{d.name}"))
    monkeypatch.setattr(rt, "learn_nickname", lambda config_path, nickname: None)
    cfg = Config(paths=PathsConfig(clips=Path("REAL"), thumbnails=Path("ELSEWHERE")))
    process = rt.make_process_window(
        cfg, Path("ffmpeg"), game_mode="battle_royale", k_templates=None, a_templates=None,
        hwaccel=None, config_path=None,
    )
    return process, calls


def test_process_window_writes_into_the_staging_folder_with_the_window_bounds(monkeypatch, tmp_path: Path):
    process, calls = _process(monkeypatch, lambda: [tmp_path / "a.json"])
    window = _window()
    cancel = threading.Event()

    written = process(Path("bg_1049590_x"), window, tmp_path / "stage", cancel)

    assert written == [tmp_path / "a.json"]
    assert calls["session"] == "session:bg_1049590_x"
    assert (calls["start"], calls["end"]) == (window.hud_start_utc, window.end_utc)
    assert calls["result_search_from"] == window.hud_end_utc
    assert calls["clips_dir"] == tmp_path / "stage"
    assert calls["cfg"].paths.thumbnails is None
    assert calls["cancel"] is cancel


def test_a_detection_cancel_becomes_a_game_cancel(monkeypatch, tmp_path: Path):
    def raise_cancel():
        raise DetectionCancelled()

    process, _ = _process(monkeypatch, raise_cancel)

    with pytest.raises(GameCancelled):
        process(Path("bg_1049590_x"), _window(5), tmp_path, None)


def test_missing_segments_produce_no_clips_instead_of_a_crash(monkeypatch, tmp_path: Path):
    def raise_cut():
        raise ClipCutError("세그먼트 없음")

    process, _ = _process(monkeypatch, raise_cut)

    assert process(Path("bg_1049590_x"), _window(5), tmp_path, None) == []


def test_scanner_lists_only_eternal_return_sessions(tmp_path: Path):
    for name in ["bg_1049590_20260923_095917", "bg_5075020_20260904_061655"]:
        (tmp_path / name).mkdir()

    scanner = rt.SteamSessionScanner(tmp_path, Path("ffmpeg"), state_dir=tmp_path / "state")

    assert [p.name for p in scanner.list_sessions()] == ["bg_1049590_20260923_095917"]


def test_scanner_returns_nothing_for_a_session_it_cannot_read(tmp_path: Path):
    broken = tmp_path / "bg_1049590_20260923_095917"
    broken.mkdir()
    scanner = rt.SteamSessionScanner(tmp_path, Path("ffmpeg"), state_dir=tmp_path / "state")

    assert scanner.scan(broken, None, lambda fraction, message: None) == []


def test_session_video_seconds_counts_segments_without_decoding(tmp_path: Path):
    session_dir = tmp_path / "bg_1049590_20260923_095917"
    session_dir.mkdir()
    for n in range(1, 4):
        (session_dir / f"chunk-stream0-{n:05d}.m4s").write_bytes(b"x")
    (session_dir / "chunk-stream1-00001.m4s").write_bytes(b"x")  # 다른 스트림은 안 센다
    (session_dir / "session.mpd").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="dynamic"
     availabilityStartTime="2026-09-23T09:59:17Z" timeShiftBufferDepth="PT2H0M0.0S">
    <Period id="0" start="PT0.0S">
        <AdaptationSet id="0" contentType="video" maxWidth="64" maxHeight="48">
            <Representation id="0" mimeType="video/mp4" width="64" height="48">
                <SegmentTemplate timescale="1000000" duration="3000000"
                                 initialization="init-stream$RepresentationID$.m4s"
                                 media="chunk-stream$RepresentationID$-$Number%05d$.m4s" startNumber="1"/>
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>""",
        encoding="utf-8",
    )

    assert rt.session_video_seconds(session_dir) == pytest.approx(9.0)


def test_session_video_seconds_is_zero_for_a_folder_it_cannot_read():
    assert rt.session_video_seconds(Path("does/not/exist")) == 0.0


def test_scanner_session_video_seconds_delegates_to_the_module_helper(tmp_path: Path, monkeypatch):
    scanner = rt.SteamSessionScanner(tmp_path, Path("ffmpeg"), state_dir=tmp_path / "state")
    monkeypatch.setattr(rt, "session_video_seconds", lambda d: 42.0)

    assert scanner.session_video_seconds(tmp_path / "whatever") == 42.0


def test_process_window_forwards_on_progress_to_process_match(monkeypatch, tmp_path: Path):
    process, calls = _process(monkeypatch, lambda: [])
    seen = []

    process(Path("bg_1049590_x"), _window(), tmp_path / "stage", None, on_progress=seen.append)
    calls["on_progress"](0.5)

    assert seen == [0.5]


def test_process_window_on_progress_defaults_to_none(monkeypatch, tmp_path: Path):
    process, calls = _process(monkeypatch, lambda: [])

    process(Path("bg_1049590_x"), _window(), tmp_path / "stage", None)

    assert calls["on_progress"] is None


def test_process_window_passes_the_clip_ids_that_already_exist_for_that_game(monkeypatch, tmp_path: Path):
    calls = {}
    monkeypatch.setattr(rt, "process_match", lambda *a, **kw: calls.update(kw) or [])
    monkeypatch.setattr(rt.RecordingSession, "load", classmethod(lambda cls, d: "session"))
    monkeypatch.setattr(rt, "learn_nickname", lambda *a: None)
    seen = []
    process = rt.make_process_window(
        Config(paths=PathsConfig(clips=Path("REAL"))), Path("ffmpeg"), k_templates=None, a_templates=None,
        hwaccel=None, config_path=None, existing_clip_ids=lambda w: seen.append(w) or {"x_01"},
    )
    window = _window()

    process(Path("bg_1049590_x"), window, tmp_path, None)

    assert seen == [window] and calls["existing_clip_ids"] == {"x_01"}
