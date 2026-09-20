import numpy as np
import pytest

from lumia_briefing_room.detect.glyph import build_template
from lumia_briefing_room.detect.match import analyze_frame, detect_match, finalize_match
from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.frames import crop_roi
from lumia_briefing_room.video.segments import SegmentRange
from lumia_briefing_room.video.session import RecordingSession

FFMPEG_PATH = None
try:
    from lumia_briefing_room.config import discover_ffmpeg

    FFMPEG_PATH = discover_ffmpeg()
except Exception:  # pragma: no cover
    FFMPEG_PATH = None

requires_ffmpeg = pytest.mark.skipif(FFMPEG_PATH is None, reason="ffmpeg를 찾을 수 없다")


def fs(t, combat, *, k=0, a=0, day_night="day", face=(111.0, 26.0)):
    return FrameState(t=t, combat=combat, face_value=face[0], face_sat=face[1], k=k, a=a, day_night=day_night)


def _paint(frame: np.ndarray, roi, rgb) -> None:
    frame[roi.y0 : roi.y1, roi.x0 : roi.x1] = rgb


def test_analyze_frame_reads_badge_face_daynight_without_templates():
    profile = ResolutionProfile.builtin(2560, 1440)
    frame = np.full((1440, 2560, 3), 80, dtype=np.uint8)
    _paint(frame, profile.rois["badge"], (255, 150, 20))
    _paint(frame, profile.rois["face"], (120, 100, 90))
    _paint(frame, profile.rois["day_night"], (255, 200, 20))

    state = analyze_frame(frame, profile, t=42.0)

    assert state.t == 42.0
    assert state.combat is True
    assert state.face_value == 120.0
    assert state.face_sat == 30.0
    assert state.day_night == "day"
    assert state.k is None
    assert state.a is None


def test_analyze_frame_reads_counter_with_templates(render_digit, compose):
    profile = ResolutionProfile.builtin(2560, 1440)
    k_roi = profile.rois["k_value"]
    height, width = k_roi.height, k_roi.width

    rng = np.random.default_rng(3)
    templates = {}
    for digit in range(10):
        alpha = render_digit(digit, height=height, width=width)
        samples = [
            compose(alpha, tuple(int(x) for x in rng.integers(0, 150, size=3)))
            for _ in range(15)
        ]
        templates[digit] = build_template(np.stack(samples))

    frame = np.full((1440, 2560, 3), 80, dtype=np.uint8)
    patch = compose(render_digit(7, height=height, width=width), (60, 40, 90))
    frame[k_roi.y0 : k_roi.y1, k_roi.x0 : k_roi.x1] = patch

    state = analyze_frame(frame, profile, t=0.0, k_templates=templates)

    assert state.k == 7
    assert state.a is None


def test_finalize_match_tags_kill():
    times = [0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33]
    combat_on = {6, 9, 12, 15, 18, 21, 24}
    k_values = {0: 0, 3: 0, 6: 0, 9: 0, 12: 1, 15: 1, 18: 1, 21: 1, 24: 1, 27: 1, 30: 1, 33: 1}
    states = [fs(t, t in combat_on, k=k_values[t]) for t in times]

    result = finalize_match(states)

    assert len(result.intervals) == 1
    interval = result.intervals[0]
    assert interval.start == 6
    assert interval.end == 24
    assert interval.k_delta == 1
    assert interval.a_delta == 0
    assert not interval.died
    assert interval.tags == frozenset({"kill"})
    assert interval.day_night == "day"
    assert result.k_final == 1
    assert result.a_final == 0


def test_finalize_match_tags_assist():
    times = [0, 3, 6, 9, 12, 15, 18, 21, 24]
    combat_on = {6, 9, 12, 15, 18}
    a_values = {0: 0, 3: 0, 6: 0, 9: 0, 12: 1, 15: 1, 18: 1, 21: 1, 24: 1}
    states = [fs(t, t in combat_on, a=a_values[t]) for t in times]

    result = finalize_match(states)

    assert len(result.intervals) == 1
    assert result.intervals[0].tags == frozenset({"assist"})
    assert result.intervals[0].a_delta == 1


def test_finalize_match_tags_death_when_face_drops_during_combat():
    times = [float(i * 3) for i in range(14)]
    combat_on = set(times[2:9])  # t=6..24
    dead_at = set(times[4:7])  # t=12..18, combat 구간 내부

    states = []
    for t in times:
        combat = t in combat_on
        if t in dead_at:
            face = (34.0, 13.0)
        else:
            face = (111.0, 26.0)
        states.append(fs(t, combat, k=0, a=0, face=face))

    result = finalize_match(states)

    assert len(result.intervals) == 1
    interval = result.intervals[0]
    assert interval.died is True
    assert "death" in interval.tags


def test_finalize_match_tags_no_result_when_nothing_happens():
    times = [0, 3, 6, 9, 12]
    combat_on = {3, 6, 9}
    states = [fs(t, t in combat_on) for t in times]

    result = finalize_match(states)

    assert len(result.intervals) == 1
    assert result.intervals[0].tags == frozenset({"no_result"})


def test_finalize_match_reports_gaps_and_source_incomplete():
    states = [fs(0, False), fs(3, True), fs(6, True)]
    gaps = [(30.0, 40.0)]

    result = finalize_match(states, gaps=gaps)

    assert result.gaps == gaps
    assert result.source_incomplete is True


def test_finalize_match_no_gaps_means_not_incomplete():
    states = [fs(0, False), fs(3, True)]
    result = finalize_match(states, gaps=[])
    assert result.source_incomplete is False


def test_finalize_match_empty_states():
    result = finalize_match([], gaps=[(0.0, 10.0)])
    assert result.intervals == []
    assert result.k_final is None
    assert result.a_final is None
    assert result.source_incomplete is True


@requires_ffmpeg
def test_detect_match_processes_synthetic_session_and_reports_gap(
    tmp_path, make_synthetic_session
):
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=6
    )
    (session_dir / "chunk-stream0-00004.m4s").unlink()
    session = RecordingSession.load(session_dir)

    result = detect_match(
        session,
        SegmentRange(first=1, last=6),
        ffmpeg_path=FFMPEG_PATH,
    )

    assert result.source_incomplete is True
    assert result.gaps == [(3.0, 4.0)]
