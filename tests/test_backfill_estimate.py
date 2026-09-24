from datetime import datetime, timezone
from pathlib import Path

import pytest

from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.pipeline import backfill_runtime as rt
from lumia_briefing_room.pipeline.vod_store import StateCache


def _session(root: Path, name: str, segments: int, segment_bytes: int = 100) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "init-stream0.m4s").write_bytes(b"i")
    for n in range(1, segments + 1):
        (folder / f"chunk-stream0-{n:05d}.m4s").write_bytes(b"x" * segment_bytes)
        (folder / f"chunk-stream1-{n:05d}.m4s").write_bytes(b"a" * 10)
    (folder / f"chunk-stream0-{segments + 1:05d}.m4s.tmp").write_bytes(b"partial")
    return folder


def _state(t: float) -> FrameState:
    return FrameState(t=t, combat=None, face_value=None, face_sat=None, k=None, a=None, day_night=None)


def test_estimate_counts_only_eternal_return_video_segments(tmp_path: Path):
    _session(tmp_path, "bg_1049590_20260923_095917", 10)
    _session(tmp_path, "bg_5075020_20260904_061655", 99)

    info = rt.estimate_backfill(tmp_path, tmp_path / "state")

    assert info["sessions"] == 1
    assert info["segments"] == 10
    assert info["videoSeconds"] == pytest.approx(30.0)
    assert info["sizeBytes"] == 10 * 100 + 10 * 10 + 1, "영상·오디오 조각과 init 을 합친다(임시 파일 제외)"


def test_estimate_is_zero_for_a_missing_or_empty_folder(tmp_path: Path):
    for root in (tmp_path / "nope", tmp_path):
        info = rt.estimate_backfill(root, tmp_path / "state")
        assert info["sessions"] == 0 and info["estimatedSeconds"] == 0.0


def test_already_scanned_segments_do_not_add_to_the_estimate(tmp_path: Path):
    _session(tmp_path, "bg_1049590_20260923_095917", 400)
    cold = rt.estimate_backfill(tmp_path, tmp_path / "state")

    cache = StateCache(tmp_path / "state" / f"scan-v{rt.ANALYSIS_VERSION}" / "bg_1049590_20260923_095917.states.jsonl.gz")
    cache.append([_state(n * 3.0) for n in range(300)])
    warm = rt.estimate_backfill(tmp_path, tmp_path / "state")

    assert cold["unscannedSeconds"] == pytest.approx(1200.0)
    assert warm["unscannedSeconds"] == pytest.approx(300.0)
    assert warm["estimatedSeconds"] < cold["estimatedSeconds"]


def test_estimate_scales_with_the_measured_speed(tmp_path: Path):
    _session(tmp_path, "bg_1049590_20260923_095917", 1200)

    info = rt.estimate_backfill(tmp_path, tmp_path / "state")

    assert info["estimatedSeconds"] == pytest.approx(info["unscannedSeconds"] / rt.ESTIMATE_SPEEDUP)
    assert rt.ESTIMATE_SPEEDUP > 1
