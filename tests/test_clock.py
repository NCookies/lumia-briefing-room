import numpy as np

from lumia_briefing_room.detect.clock import read_clock_zero
from lumia_briefing_room.detect.match import analyze_frame, finalize_match
from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.profiles.models import ResolutionProfile

H, W = 28, 80
STARTS = [0.0625, 0.2375, 0.625, 0.8]


def ring(h=20, w=10):
    glyph = np.zeros((h, w), dtype=np.uint8)
    glyph[:, :2] = glyph[:, -2:] = 255
    glyph[:2, :] = glyph[-2:, :] = 255
    return glyph


def bar(h=20, w=10):
    glyph = np.zeros((h, w), dtype=np.uint8)
    glyph[:, w // 2 - 1 : w // 2 + 1] = 255
    return glyph


def clock(glyphs, background=(30, 40, 50)):
    frame = np.zeros((H, W, 3), dtype=np.uint8)
    frame[:] = background
    for a, glyph in zip(STARTS, glyphs):
        x0 = int(a * W)
        h, w = glyph.shape
        frame[4 : 4 + h, x0 : x0 + w] = glyph[..., None]
    return frame


def test_all_four_digits_alike_reads_as_zero_clock():
    assert read_clock_zero(clock([ring(), ring(), ring(), ring()])) is True


def test_a_different_digit_means_the_clock_is_running():
    assert read_clock_zero(clock([ring(), bar(), ring(), ring()])) is False
    assert read_clock_zero(clock([ring(), ring(), ring(), bar()])) is False


def test_no_clock_visible_is_unknown():
    assert read_clock_zero(np.full((H, W, 3), 20, dtype=np.uint8)) is None


def frame_state(t, *, combat, clock_zero):
    return FrameState(
        t=float(t), combat=combat, face_value=110.0, face_sat=25.0, k=0, a=0,
        day_night="day", spectating=False, game_day=1, clock_zero=clock_zero,
    )


def test_a_long_run_of_zero_clock_frames_is_a_waiting_room_not_a_fight():
    states = [frame_state(t, combat=True, clock_zero=True) for t in range(0, 10)]
    states += [frame_state(t, combat=False, clock_zero=False) for t in range(10, 40)]
    states += [frame_state(t, combat=True, clock_zero=False) for t in range(40, 50)]

    result = finalize_match(states)

    assert [(iv.start, iv.end) for iv in result.intervals] == [(40.0, 49.0)]


def test_a_brief_zero_clock_flash_between_phases_does_not_cut_a_fight():
    states = [frame_state(t, combat=True, clock_zero=False) for t in range(0, 30)]
    for t in (14, 15):
        states[t] = frame_state(t, combat=True, clock_zero=True)

    result = finalize_match(states)

    assert [(iv.start, iv.end) for iv in result.intervals] == [(0.0, 29.0)]


def test_waiting_room_is_excluded_even_when_a_kill_counter_reads_zero():
    states = [frame_state(t, combat=None, clock_zero=True) for t in range(0, 12)]
    states += [frame_state(t, combat=False, clock_zero=False) for t in range(12, 20)]

    assert finalize_match(states).intervals == []


def test_analyze_frame_reads_the_clock_only_for_profiles_that_have_the_roi():
    with_roi = ResolutionProfile.for_resolution(1920, 1080)
    steam = ResolutionProfile.for_resolution(2560, 1440)
    assert "timer" in with_roi.rois and "timer" not in steam.rois

    frame = np.full((1080, 1920, 3), 20, dtype=np.uint8)
    assert analyze_frame(frame, with_roi, t=1.0).clock_zero is None
    assert analyze_frame(np.full((1440, 2560, 3), 20, dtype=np.uint8), steam, t=1.0).clock_zero is None
