from datetime import datetime, timezone

import pytest

from lumia_briefing_room.config import ClipConfig, discover_ffmpeg
from lumia_briefing_room.detect.types import CombatInterval
from lumia_briefing_room.pipeline.clip import (
    ClipCutError,
    ClipRange,
    cut_clip,
    make_thumbnail,
    merge_overlapping,
    resolve_clip_range,
)
from lumia_briefing_room.video.session import RecordingSession

FFMPEG_PATH = discover_ffmpeg()
requires_ffmpeg = pytest.mark.skipif(FFMPEG_PATH is None, reason="ffmpeg를 찾을 수 없다")


def ci(start, end, *, team_combat_unreliable=False):
    return CombatInterval(
        start=start, end=end, tags=frozenset({"kill"}),
        k_delta=1, a_delta=0, died=False, day_night="day", confidence=1.0,
        team_combat_unreliable=team_combat_unreliable,
    )


def test_resolve_clip_range_applies_preroll_and_postroll():
    cfg = ClipConfig(preroll_sec=5, postroll_sec=8)
    r = resolve_clip_range(ci(100, 120), cfg)
    assert r.start == 95
    assert r.end == 128
    assert r.preroll_source == "combat"


def test_resolve_clip_range_clamps_start_at_zero():
    cfg = ClipConfig(preroll_sec=30, postroll_sec=8)
    r = resolve_clip_range(ci(10, 20), cfg)
    assert r.start == 0


def test_resolve_clip_range_never_truncates_a_long_fight():
    # 2026-09-24 실사용: 126초 교전이 90초 상한에 뒷부분(추격 장면)이 잘렸다. 상한은 두지 않는다.
    cfg = ClipConfig(preroll_sec=5, postroll_sec=8)
    r = resolve_clip_range(ci(100, 226), cfg)
    assert r.start == 95
    assert r.end == 234


def test_resolve_clip_range_widens_preroll_when_team_combat_was_unreliable():
    # 2026-09-23: 팀원 링 오탐으로 배지만으로 잘린 매치는 구도 잡는 구간을 놓치기 쉽다
    # (pipeline/clip.py resolve_clip_range 주석 참고). fixed_preroll_sec 로 더 넉넉히 준다.
    cfg = ClipConfig(preroll_sec=5, postroll_sec=8, fixed_preroll_sec=30)

    r = resolve_clip_range(ci(100, 120, team_combat_unreliable=True), cfg)

    assert r.start == 70
    assert r.end == 128
    assert r.preroll_source == "fixed"


def test_resolve_clip_range_keeps_the_normal_preroll_when_team_combat_was_reliable():
    cfg = ClipConfig(preroll_sec=5, postroll_sec=8, fixed_preroll_sec=30)

    r = resolve_clip_range(ci(100, 120, team_combat_unreliable=False), cfg)

    assert r.start == 95
    assert r.preroll_source == "combat"


def test_merge_overlapping_merges_close_ranges():
    ranges = [ClipRange(0, 20, "combat"), ClipRange(25, 40, "combat")]
    merged = merge_overlapping(ranges, gap=10)
    assert merged == [ClipRange(0, 40, "combat")]


def test_merge_overlapping_keeps_distant_ranges_separate():
    ranges = [ClipRange(0, 20, "combat"), ClipRange(100, 120, "combat")]
    merged = merge_overlapping(ranges, gap=10)
    assert merged == [ClipRange(0, 20, "combat"), ClipRange(100, 120, "combat")]


def test_merge_overlapping_handles_actual_overlap():
    ranges = [ClipRange(0, 30, "combat"), ClipRange(20, 50, "combat")]
    merged = merge_overlapping(ranges, gap=0)
    assert merged == [ClipRange(0, 50, "combat")]


def test_merge_overlapping_sorts_unordered_input():
    ranges = [ClipRange(50, 60, "combat"), ClipRange(0, 10, "combat")]
    merged = merge_overlapping(ranges, gap=0)
    assert merged == [ClipRange(0, 10, "combat"), ClipRange(50, 60, "combat")]


def test_merge_overlapping_empty_input():
    assert merge_overlapping([], gap=10) == []


def test_merge_overlapping_single_range():
    ranges = [ClipRange(0, 10, "combat")]
    assert merge_overlapping(ranges, gap=10) == ranges


@requires_ffmpeg
def test_cut_clip_produces_valid_output(tmp_path, make_synthetic_session):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=10,
        start_utc=start,
    )
    session = RecordingSession.load(session_dir)
    out_path = tmp_path / "clip.mp4"

    result = cut_clip(
        session, ClipRange(1.0, 5.0, "combat"), out_path, ffmpeg_path=FFMPEG_PATH,
    )

    assert out_path.exists() and out_path.stat().st_size > 0
    assert result.source_incomplete is False
    assert result.segment_start <= result.segment_end


@requires_ffmpeg
def test_cut_clip_marks_source_incomplete_on_gap(tmp_path, make_synthetic_session):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=10,
        start_utc=start,
    )
    (session_dir / "chunk-stream0-00003.m4s").unlink()
    session = RecordingSession.load(session_dir)
    out_path = tmp_path / "clip.mp4"

    result = cut_clip(
        session, ClipRange(0.0, 9.0, "combat"), out_path, ffmpeg_path=FFMPEG_PATH,
    )

    assert result.source_incomplete is True


@requires_ffmpeg
def test_cut_clip_raises_when_nothing_exists(tmp_path, make_synthetic_session):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=3,
        start_utc=start,
    )
    session = RecordingSession.load(session_dir)

    with pytest.raises(ClipCutError):
        cut_clip(
            session, ClipRange(1000.0, 1010.0, "combat"), tmp_path / "clip.mp4",
            ffmpeg_path=FFMPEG_PATH,
        )


@requires_ffmpeg
def test_make_thumbnail_creates_image_with_requested_width(tmp_path, make_synthetic_session):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=5,
        start_utc=start,
    )
    session = RecordingSession.load(session_dir)
    clip_path = tmp_path / "clip.mp4"
    cut_clip(session, ClipRange(0.0, 5.0, "combat"), clip_path, ffmpeg_path=FFMPEG_PATH)

    thumb_path = tmp_path / "thumb.jpg"
    make_thumbnail(
        clip_path, thumb_path, duration_sec=5.0, offset_ratio=0.5, width=32,
        ffmpeg_path=FFMPEG_PATH,
    )

    assert thumb_path.exists() and thumb_path.stat().st_size > 0


def test_audio_input_args_delay_audio_that_starts_after_the_video():
    from lumia_briefing_room.pipeline.clip import audio_input_args

    assert audio_input_args([10, 11, 12], [13, 14], 3.0) == ["-itsoffset", "9.000"]


def test_audio_input_args_trim_audio_that_starts_before_the_video():
    from lumia_briefing_room.pipeline.clip import audio_input_args

    assert audio_input_args([12, 13], [10, 11, 12, 13], 3.0) == ["-ss", "6.000"]


def test_audio_input_args_empty_when_audio_and_video_start_together():
    from lumia_briefing_room.pipeline.clip import audio_input_args

    assert audio_input_args([10, 11], [10, 11], 3.0) == []


def test_audio_status_full_partial_none():
    from lumia_briefing_room.pipeline.clip import audio_status

    assert audio_status([10, 11, 12], [10, 11, 12]) == "full"
    assert audio_status([10, 11, 12], [9, 10, 11, 12, 13]) == "full"
    assert audio_status([10, 11, 12], [11, 12]) == "partial"
    assert audio_status([10, 11, 12], [10, 11]) == "partial"
    assert audio_status([10, 11, 12], []) == "none"
