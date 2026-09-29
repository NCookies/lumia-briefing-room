import dataclasses

import numpy as np
import pytest

from lumia_briefing_room.detect.glyph import build_template
from lumia_briefing_room.detect.match import analyze_frame, detect_match, finalize_match
from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.profiles.models import ResolutionProfile, Roi
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


def fs(t, combat, *, k=0, a=0, tk=0, day_night="day", face=(111.0, 26.0)):
    return FrameState(t=t, combat=combat, face_value=face[0], face_sat=face[1], k=k, a=a, tk=tk, day_night=day_night)


def _paint(frame: np.ndarray, roi, rgb) -> None:
    frame[roi.y0 : roi.y1, roi.x0 : roi.x1] = rgb


def _alive_frame(profile, background=80) -> np.ndarray:
    """미니맵 헤더 + 내 체력바(초록)를 그려 spectating=False 가 되는 "정상 플레이 중" 프레임.

    analyze_frame 은 spectating 이 확실히 False 일 때만 배지/얼굴을 읽는다(2026-09-23
    수정 - 로딩/캐릭터 선택 화면이 사망으로 오판되던 문제, spectating=None 도 안전하게
    걸러야 한다). 배지·얼굴을 재는 테스트는 전부 이 프레임 위에서 그려야 한다.
    """
    frame = np.full((profile.height, profile.width, 3), background, dtype=np.uint8)
    header = profile.rois["minimap_icons"]
    frame[header.y0 + 5 : header.y1 - 5, header.x0 : header.x1] = 210
    strip = profile.rois["hp_strip"]
    mid_y = (strip.y0 + strip.y1) // 2
    frame[mid_y - 5 : mid_y + 5, strip.x0 : strip.x0 + 200] = (90, 220, 40)
    return frame


def test_analyze_frame_reads_badge_face_daynight_without_templates():
    profile = ResolutionProfile.builtin(2560, 1440)
    frame = _alive_frame(profile)
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


def test_analyze_frame_reads_tk_with_resized_k_templates(render_digit, compose):
    from lumia_briefing_room.detect.match import resolve_tk_templates

    profile = ResolutionProfile.builtin(2560, 1440)
    k_roi = profile.rois["k_value"]
    height, width = k_roi.height, k_roi.width

    rng = np.random.default_rng(3)
    k_templates = {}
    for digit in range(10):
        alpha = render_digit(digit, height=height, width=width)
        samples = [
            compose(alpha, tuple(int(x) for x in rng.integers(0, 150, size=3)))
            for _ in range(15)
        ]
        k_templates[digit] = build_template(np.stack(samples))
    tk_templates = resolve_tk_templates(profile, k_templates)

    tk_roi = profile.rois["tk_value"]
    frame = np.full((1440, 2560, 3), 80, dtype=np.uint8)
    patch = compose(render_digit(5, height=tk_roi.height, width=tk_roi.width), (60, 40, 90))
    frame[tk_roi.y0 : tk_roi.y1, tk_roi.x0 : tk_roi.x1] = patch

    state = analyze_frame(frame, profile, t=0.0, tk_templates=tk_templates)

    assert state.tk == 5
    assert state.a is None


def _digit_templates(rng_seed, height, width, render_digit, compose):
    rng = np.random.default_rng(rng_seed)
    templates = {}
    for digit in range(10):
        alpha = render_digit(digit, height=height, width=width)
        samples = [
            compose(alpha, tuple(int(x) for x in rng.integers(0, 150, size=3)))
            for _ in range(15)
        ]
        templates[digit] = build_template(np.stack(samples))
    return templates


def _paint_digit_at_native_scale(frame, native_roi, ref_height, ref_width, digit, render_digit, compose):
    """본보기는 기준 해상도(예: k_value 36x24)로 만들어지는데, `render_digit` 은 캔버스
    크기와 무관하게 고정된 절대 글자 크기로 그린다(conftest.py) - 기준 크기로 그린 뒤
    ROI 의 실제(네이티브) 크기로 줄여 붙여야 `_crop_for_reference`가 다시 키웠을 때
    본보기와 같은 상대적 위치·크기가 된다(실제 압축 영상을 원본 해상도로 찍은 것과
    같은 축소를 흉내낸다)."""
    import cv2

    ref_patch = compose(render_digit(digit, height=ref_height, width=ref_width), (60, 40, 90))
    native_patch = cv2.resize(
        ref_patch, (native_roi.width, native_roi.height), interpolation=cv2.INTER_CUBIC
    )
    frame[native_roi.y0 : native_roi.y1, native_roi.x0 : native_roi.x1] = native_patch


def test_analyze_frame_reads_k_and_a_from_the_cobalt_hud_position(render_digit, compose):
    """코발트 프로토콜은 같은 스트리머의 배틀로얄 녹화 대비 TK/K/A 가 ~80px 왼쪽에 있다
    (실측, 2026-09-27, plan.md §10-3 후속) - 배틀로얄 자리가 비어 있으면 코발트 자리를
    기준 해상도 크기로 키워 다시 읽는다. 본보기는 기준 해상도(2560x1440) 본보기(k_value
    등)를 그대로 쓴다(실제 운영 코드가 쓰는 것과 같은 본보기)."""
    ref_profile = ResolutionProfile.builtin(2560, 1440)
    profile = ResolutionProfile.for_resolution(1920, 1080)
    k_ref_roi = ref_profile.rois["k_value"]
    a_ref_roi = ref_profile.rois["a_value"]
    k_templates = _digit_templates(3, k_ref_roi.height, k_ref_roi.width, render_digit, compose)
    a_templates = _digit_templates(4, a_ref_roi.height, a_ref_roi.width, render_digit, compose)

    frame = np.full((1080, 1920, 3), 80, dtype=np.uint8)
    _paint_digit_at_native_scale(
        frame, profile.rois["cobalt_k_value"], k_ref_roi.height, k_ref_roi.width, 7, render_digit, compose
    )
    _paint_digit_at_native_scale(
        frame, profile.rois["cobalt_a_value"], a_ref_roi.height, a_ref_roi.width, 9, render_digit, compose
    )

    state = analyze_frame(frame, profile, t=0.0, k_templates=k_templates, a_templates=a_templates)

    assert state.k == 7
    assert state.a == 9


def test_analyze_frame_reads_tk_from_the_cobalt_hud_position(render_digit, compose):
    from lumia_briefing_room.detect.match import resolve_tk_templates

    ref_profile = ResolutionProfile.builtin(2560, 1440)
    profile = ResolutionProfile.for_resolution(1920, 1080)
    k_ref_roi = ref_profile.rois["k_value"]
    k_templates = _digit_templates(3, k_ref_roi.height, k_ref_roi.width, render_digit, compose)
    tk_templates = resolve_tk_templates(profile, k_templates)
    tk_ref_roi = ref_profile.rois["tk_value"]

    frame = np.full((1080, 1920, 3), 80, dtype=np.uint8)
    _paint_digit_at_native_scale(
        frame, profile.rois["cobalt_tk_value"], tk_ref_roi.height, tk_ref_roi.width, 5, render_digit, compose
    )

    state = analyze_frame(frame, profile, t=0.0, tk_templates=tk_templates)

    assert state.tk == 5


def test_analyze_frame_battle_royale_position_wins_over_cobalt_when_both_present(render_digit, compose):
    """두 자리 모두 판독되면(있을 수 없는 상황이지만 방어적으로) 배틀로얄 자리를 우선한다 -
    코발트 자리는 그 자리에 실제로 숫자가 없을 때만 보는 대체 경로다."""
    ref_profile = ResolutionProfile.builtin(2560, 1440)
    profile = ResolutionProfile.for_resolution(1920, 1080)
    k_ref_roi = ref_profile.rois["k_value"]
    k_templates = _digit_templates(3, k_ref_roi.height, k_ref_roi.width, render_digit, compose)

    frame = np.full((1080, 1920, 3), 80, dtype=np.uint8)
    _paint_digit_at_native_scale(
        frame, profile.rois["k_value"], k_ref_roi.height, k_ref_roi.width, 2, render_digit, compose
    )
    _paint_digit_at_native_scale(
        frame, profile.rois["cobalt_k_value"], k_ref_roi.height, k_ref_roi.width, 8, render_digit, compose
    )

    state = analyze_frame(frame, profile, t=0.0, k_templates=k_templates)

    assert state.k == 2


def test_analyze_frame_k_stays_none_when_neither_hud_position_has_a_digit(render_digit, compose):
    ref_profile = ResolutionProfile.builtin(2560, 1440)
    profile = ResolutionProfile.for_resolution(1920, 1080)
    k_ref_roi = ref_profile.rois["k_value"]
    k_templates = _digit_templates(3, k_ref_roi.height, k_ref_roi.width, render_digit, compose)

    frame = np.full((1080, 1920, 3), 80, dtype=np.uint8)

    assert analyze_frame(frame, profile, t=0.0, k_templates=k_templates).k is None


def test_analyze_frame_detects_alive_via_cobalt_minimap_icons_position():
    """미니맵 헤더 아이콘도 코발트 자리가 배틀로얄과 다르다(실측, 코발트.mp4 2026-09-29) -
    기본 자리가 비어 있어도 코발트 자리에 아이콘이 보이면 로비/암전(None)으로 새면
    안 된다(그러면 얼굴/배지를 아예 안 읽어 사망 검출이 통째로 죽는다)."""
    profile = ResolutionProfile.for_resolution(1920, 1080)
    frame = np.full((profile.height, profile.width, 3), 80, dtype=np.uint8)
    cobalt_header = profile.rois["cobalt_minimap_icons"]
    frame[cobalt_header.y0 + 2 : cobalt_header.y1 - 2, cobalt_header.x0 : cobalt_header.x1] = 210
    strip = profile.rois["hp_strip"]
    mid_y = (strip.y0 + strip.y1) // 2
    frame[mid_y - 5 : mid_y + 5, strip.x0 : strip.x0 + 200] = (90, 220, 40)

    state = analyze_frame(frame, profile, t=0.0)

    assert state.spectating is False


def test_analyze_frame_also_reads_cobalt_face_position_when_configured():
    """얼굴 ROI 도 코발트 자리가 배틀로얄과 다르다(실측, 코발트.mp4 2026-09-29) - game_mode
    를 프레임 하나로는 아직 모르므로 두 자리를 모두 재두고, finalize_match 가 game_mode
    를 알아낸 뒤에 고른다. 실측 좌표는 face 자리와 겹치므로(둘 다 캐릭터 상반신 쪽), 이
    테스트에서는 겹치지 않는 임의 자리로 바꿔 두 값이 섞이지 않고 각자 읽히는지만 본다."""
    profile = ResolutionProfile.for_resolution(1920, 1080)
    moved_cobalt_face = Roi(1000, 100, 1050, 150)
    profile = dataclasses.replace(profile, rois={**profile.rois, "cobalt_face": moved_cobalt_face})
    frame = _alive_frame(profile)
    _paint(frame, profile.rois["face"], (60, 40, 30))
    _paint(frame, moved_cobalt_face, (120, 200, 210))

    state = analyze_frame(frame, profile, t=0.0)

    assert (state.face_value, state.face_sat) == (60.0, 30.0)
    assert (state.cobalt_face_value, state.cobalt_face_sat) == (210.0, 90.0)


def test_analyze_frame_cobalt_face_is_none_without_the_roi():
    profile = ResolutionProfile.builtin(2560, 1440)
    frame = _alive_frame(profile)
    _paint(frame, profile.rois["face"], (60, 40, 30))

    state = analyze_frame(frame, profile, t=0.0)

    assert state.cobalt_face_value is None
    assert state.cobalt_face_sat is None


def test_calibrate_counter_position_finds_a_shifted_k_value(render_digit, compose):
    """실사용 보고(2026-09-28): 같은 해상도(1920x1080)인데도 영상마다 TK/K/A 칸 위치가
    달랐다(스트리머 VOD의 코발트 vs 배틀로얄). 매번 사람이 좌표를 실측해 하드코딩하는
    대신, 기본 자리가 안 맞으면 그 주변 넓은 영역에서 자동으로 찾는다(plan.md §10-13)."""
    from lumia_briefing_room.detect.match import calibrate_counter_position

    ref_profile = ResolutionProfile.builtin(2560, 1440)
    profile = ResolutionProfile.for_resolution(1920, 1080)
    k_ref_roi = ref_profile.rois["k_value"]
    k_templates = _digit_templates(3, k_ref_roi.height, k_ref_roi.width, render_digit, compose)

    k_roi = profile.rois["k_value"]
    dx, dy = -80, -3
    shifted = Roi(k_roi.x0 + dx, k_roi.y0 + dy, k_roi.x1 + dx, k_roi.y1 + dy)

    frames = []
    for _ in range(4):
        frame = np.full((1080, 1920, 3), 80, dtype=np.uint8)
        _paint_digit_at_native_scale(frame, shifted, k_ref_roi.height, k_ref_roi.width, 5, render_digit, compose)
        frames.append(frame)

    new_profile = calibrate_counter_position(profile, frames, k_templates)

    assert (new_profile.rois["k_value"].x0, new_profile.rois["k_value"].y0) == (k_roi.x0 + dx, k_roi.y0 + dy)
    # a_value/tk_value 도 같은 만큼 통째로 옮겨진다 - 세 칸은 같은 줄에 나란히 있다.
    a_roi, tk_roi = profile.rois["a_value"], profile.rois["tk_value"]
    assert new_profile.rois["a_value"].x0 == a_roi.x0 + dx
    assert new_profile.rois["tk_value"].x0 == tk_roi.x0 + dx
    # 이 프로필로 같은 자리를 다시 읽으면 이제 정상적으로 읽힌다.
    state = analyze_frame(frames[0], new_profile, t=0.0, k_templates=k_templates)
    assert state.k == 5


def test_calibrate_counter_position_is_a_no_op_when_default_position_already_works(render_digit, compose):
    ref_profile = ResolutionProfile.builtin(2560, 1440)
    profile = ResolutionProfile.for_resolution(1920, 1080)
    k_ref_roi = ref_profile.rois["k_value"]
    k_templates = _digit_templates(3, k_ref_roi.height, k_ref_roi.width, render_digit, compose)

    from lumia_briefing_room.detect.match import calibrate_counter_position

    k_roi = profile.rois["k_value"]
    frames = []
    for _ in range(4):
        frame = np.full((1080, 1920, 3), 80, dtype=np.uint8)
        _paint_digit_at_native_scale(frame, k_roi, k_ref_roi.height, k_ref_roi.width, 5, render_digit, compose)
        frames.append(frame)

    new_profile = calibrate_counter_position(profile, frames, k_templates)

    assert new_profile is profile


def test_calibrate_counter_position_gives_up_on_blank_frames(render_digit, compose):
    from lumia_briefing_room.detect.match import calibrate_counter_position

    ref_profile = ResolutionProfile.builtin(2560, 1440)
    profile = ResolutionProfile.for_resolution(1920, 1080)
    k_ref_roi = ref_profile.rois["k_value"]
    k_templates = _digit_templates(3, k_ref_roi.height, k_ref_roi.width, render_digit, compose)

    frames = [np.full((1080, 1920, 3), 80, dtype=np.uint8) for _ in range(4)]

    new_profile = calibrate_counter_position(profile, frames, k_templates)

    assert new_profile is profile


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


def test_finalize_match_extends_combat_end_to_a_trailing_teammate_kill():
    # 2026-09-23 실사용 보고: 내 배지는 9초에 꺼졌는데, 팀원이 6초 뒤(15초)에 막타를
    # 넣어 TK 가 올랐다. 클립이 그 장면 직전에 끊기는 문제라 구간 끝을 늘려야 한다.
    states = [
        fs(0, False, tk=0),
        fs(3, True, tk=0),
        fs(6, True, tk=0),
        fs(9, True, tk=0),
        fs(12, False, tk=0),
        fs(15, False, tk=1),
        fs(18, False, tk=1),
    ]

    result = finalize_match(states)

    assert len(result.intervals) == 1
    assert result.intervals[0].end == 15


def test_finalize_match_extends_combat_end_to_a_trailing_own_kill():
    states = [
        fs(0, False, k=0),
        fs(3, True, k=0),
        fs(6, True, k=0),
        fs(9, True, k=0),
        fs(12, False, k=0),
        fs(15, False, k=1),
        fs(18, False, k=1),
    ]

    result = finalize_match(states)

    assert result.intervals[0].end == 15
    assert result.intervals[0].k_delta == 1


def test_finalize_match_never_spawns_a_new_interval_from_tk_alone():
    # SPEC §2.8: TK 는 팀 전체 킬이라 내가 없는 곳의 팀원 킬까지 앵커로 쓰면(코발트
    # 프로토콜처럼 TK 가 빨리 오르는 모드에서) 가짜 클립이 쏟아진다. K/A 와 달리 TK
    # 델타 혼자서는 새 구간을 만들면 안 되고, 이미 있는 구간의 끝만 늘려야 한다.
    states = [
        fs(0, False, tk=0),
        fs(200, False, tk=0),
        fs(203, False, tk=1),  # 내 배지·팀원 전투 신호와 전혀 무관한 먼 곳의 팀킬
        fs(206, False, tk=1),
    ]

    result = finalize_match(states)

    assert result.intervals == []


def test_finalize_match_does_not_extend_past_the_trailing_kill_tolerance():
    states = [
        fs(0, False, tk=0),
        fs(3, True, tk=0),
        fs(6, True, tk=0),
        fs(9, True, tk=0),
        fs(12, False, tk=0),
        fs(15, False, tk=0),
        fs(18, False, tk=0),
        fs(21, False, tk=0),
        fs(24, False, tk=0),
        fs(27, False, tk=1),
        fs(30, False, tk=1),
    ]

    result = finalize_match(states)

    assert result.intervals[0].end == 9


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


def test_resolve_templates_loads_profile_templates_when_not_given():
    from lumia_briefing_room.detect.match import resolve_templates

    profile = ResolutionProfile.for_resolution(2560, 1440)
    assert profile.templates is not None

    k, a = resolve_templates(profile, None, None)

    assert k and a
    assert set(k) == set(a)


def test_resolve_templates_keeps_explicit_templates():
    from lumia_briefing_room.detect.match import resolve_templates

    profile = ResolutionProfile.for_resolution(2560, 1440)
    explicit = {7: np.zeros((3, 3), np.float32)}

    k, a = resolve_templates(profile, explicit, None)

    assert k is explicit
    assert a and a is not explicit


def test_resolve_tk_templates_resizes_k_templates_to_the_tk_field():
    # TK 칸(tk_value)은 K/A 와 폰트는 같지만 필드 폭이 좁다(SPEC §3, 2026-09-23 실측) -
    # 같은 검정 HUD 배경이라(R 아이콘과 달리) 리사이즈만으로 재사용된다.
    from lumia_briefing_room.detect.match import resolve_templates, resolve_tk_templates

    profile = ResolutionProfile.for_resolution(2560, 1440)
    k_templates, _ = resolve_templates(profile, None, None)

    tk_templates = resolve_tk_templates(profile, k_templates)

    roi = profile.rois["tk_value"]
    assert tk_templates
    assert tk_templates[0].shape == (roi.height, roi.width)


def test_resolve_tk_templates_is_none_without_k_templates():
    from lumia_briefing_room.detect.match import resolve_tk_templates

    profile = ResolutionProfile.for_resolution(2560, 1440)
    assert resolve_tk_templates(profile, None) is None


def test_resolve_tk_templates_matches_what_profile_crop_actually_returns():
    # 정규화 프로필(예: 1920x1080)의 profile.crop() 은 기준 해상도(2560x1440) ROI 크기로
    # 자동 확대한 크롭을 낸다 - 템플릿 크기가 그 확대된 크기와 안 맞으면 read_field 가
    # 조용히 None 만 낸다(2026-09-23 VOD 실측으로 발견한 버그).
    from lumia_briefing_room.detect.match import resolve_templates, resolve_tk_templates

    profile = ResolutionProfile.for_resolution(1920, 1080)
    k_templates, _ = resolve_templates(profile, None, None)

    tk_templates = resolve_tk_templates(profile, k_templates)

    frame = np.zeros((profile.height, profile.width, 3), dtype=np.uint8)
    actual_crop_shape = profile.crop(frame, "tk_value").shape[:2]
    assert tk_templates[0].shape == actual_crop_shape


def test_resolve_templates_warns_when_profile_has_none(caplog):
    from lumia_briefing_room.detect.match import resolve_templates

    profile = ResolutionProfile.for_resolution(1600, 900)
    assert profile.templates is None

    with caplog.at_level("WARNING"):
        k, a = resolve_templates(profile, None, None)

    assert k is None and a is None
    assert any("템플릿" in r.message for r in caplog.records)


def _spec_states(spectating_from, count, *, combat_until=12.0, step=3.0, total=15):
    states = []
    for i in range(total):
        t = i * step
        spectating = spectating_from <= t < spectating_from + count * step
        states.append(
            FrameState(
                t=t, combat=(t <= combat_until) and not spectating,
                face_value=111.0, face_sat=26.0, k=0, a=0, day_night="day",
                spectating=spectating,
            )
        )
    return states


def test_finalize_match_tags_death_when_spectator_ui_follows_combat():
    detection = finalize_match(_spec_states(15.0, 4))

    assert len(detection.intervals) == 1
    assert "death" in detection.intervals[0].tags
    assert detection.intervals[0].died is True
    assert detection.spectator_ranges == [(15.0, 24.0)]


def test_finalize_match_ignores_single_spectating_sample():
    detection = finalize_match(_spec_states(15.0, 1))

    assert detection.spectator_ranges == []
    assert "death" not in detection.intervals[0].tags


def test_finalize_match_spectator_frames_do_not_count_as_combat():
    states = _spec_states(9.0, 4, combat_until=99.0)
    detection = finalize_match(states)

    assert detection.intervals[0].end < 9.0


def test_finalize_match_spectator_far_from_combat_is_not_linked_to_it():
    detection = finalize_match(_spec_states(39.0, 2, combat_until=9.0, total=20))

    assert detection.spectator_ranges == [(39.0, 42.0)]
    assert "death" not in detection.intervals[0].tags


def _intro_states(spectating_count, *, loading_count=4, live_count=5, step=3.0):
    """로딩(spectating=None) -> 캐릭터 선택/팀 소개(spectating=True 로 오판) -> 정상 플레이."""
    states = []
    for i in range(loading_count + spectating_count + live_count):
        t = i * step
        loading = i < loading_count
        intro = not loading and i < loading_count + spectating_count
        blank = loading or intro
        states.append(
            FrameState(
                t=t, combat=None if blank else False,
                face_value=None if blank else 116.0, face_sat=None if blank else 26.0,
                k=None if blank else 0, a=None if blank else 0, day_night=None if blank else "day",
                spectating=None if loading else (True if intro else False),
            )
        )
    return states


def test_finalize_match_spectating_before_any_live_frame_is_not_a_death():
    # 2026-09-24 실사용: 경기 시작 직후 캐릭터 선택/팀 소개 화면(RANK GAME 01~08)이 "관전"으로 읽혀
    # 앞 12초가 "설명 안 되는 사망" 교전으로 뽑혔다. 죽으려면 먼저 살아 있는 화면이 있어야 한다.
    detection = finalize_match(_intro_states(7))

    assert detection.intervals == []


def test_finalize_match_spectating_after_live_frames_is_still_a_death():
    states = _intro_states(7, live_count=6)
    tail = _spec_states(0.0, 4, combat_until=-1.0, total=4)
    states += [FrameState(**{**s.__dict__, "t": (len(states) + i) * 3.0}) for i, s in enumerate(tail)]

    detection = finalize_match(states)

    assert any("death" in iv.tags for iv in detection.intervals)


def test_analyze_frame_reads_spectating_from_ui_rois():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = np.full((1440, 2560, 3), 20, np.uint8)
    header = profile.rois["minimap_icons"]
    frame[header.y0 + 20 : header.y0 + 45, header.x0 : header.x1] = 210

    state = analyze_frame(frame, profile, t=0.0)

    assert state.spectating is True
    assert state.combat is None


def test_analyze_frame_ignores_badge_and_face_on_a_hud_less_screen():
    # 2026-09-23 실사용 사고: 캐릭터 선택/로딩 화면(미니맵 자체가 없다 -> spectating=None)
    # 이 "알 수 없음 교전"으로 뽑혔다. 로딩 화면의 암전 전환이 사망 램프처럼 보여 face 값이
    # 죽음으로 오판됐다. 미니맵조차 안 보이면(spectating=None) 배지/얼굴은 아예 읽지 않는다 -
    # 관전(True)일 때와 같은 취급.
    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = np.full((1440, 2560, 3), 20, np.uint8)  # 미니맵 헤더 없음 -> spectating=None
    _paint(frame, profile.rois["badge"], (255, 150, 20))  # 배지처럼 보이는 색을 칠해도
    _paint(frame, profile.rois["face"], (10, 5, 5))  # 얼굴이 죽음처럼 어두워도

    state = analyze_frame(frame, profile, t=0.0)

    assert state.spectating is None
    assert state.combat is None
    assert state.face_value is None
    assert state.face_sat is None


def _team_state(t, combat, dead):
    return FrameState(
        t=t, combat=combat, face_value=111.0, face_sat=26.0, k=0, a=0,
        day_night="day", spectating=False, dead_teammates=dead,
    )


def test_finalize_match_tags_teammate_death_inside_combat():
    states = [
        _team_state(0.0, False, ()), _team_state(3.0, True, ()),
        _team_state(6.0, True, (1,)), _team_state(9.0, True, (1,)),
        _team_state(12.0, False, (1,)), _team_state(15.0, False, (1,)),
    ]

    detection = finalize_match(states)

    interval = detection.intervals[0]
    assert "teammate_death" in interval.tags
    assert "no_result" not in interval.tags
    assert interval.teammate_deaths == 1
    assert detection.teammate_deaths == [(6.0, 1)]


def test_finalize_match_ignores_teammate_already_dead_before_combat():
    states = [
        _team_state(0.0, False, (1,)), _team_state(3.0, True, (1,)),
        _team_state(6.0, True, (1,)), _team_state(9.0, False, (1,)),
    ]

    detection = finalize_match(states)

    assert detection.intervals[0].tags == frozenset({"no_result"})
    assert detection.teammate_deaths == []


def test_finalize_match_skips_samples_without_hud_when_tracking_teammates():
    states = [
        _team_state(0.0, False, ()), _team_state(3.0, True, None),
        _team_state(6.0, True, ()), _team_state(9.0, False, ()),
    ]

    assert finalize_match(states).teammate_deaths == []


def test_analyze_frame_reads_dead_teammate_from_bar_roi():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = np.full((1440, 2560, 3), 20, np.uint8)
    header = profile.rois["minimap_icons"]
    frame[header.y0 + 20 : header.y0 + 45, header.x0 : header.x1] = 210
    bar = profile.rois["team_bar2"]
    frame[bar.y0 : bar.y1, bar.x0 : bar.x0 + 10] = (240, 150, 30)

    state = analyze_frame(frame, profile, t=0.0)

    assert state.dead_teammates == (1,)


def test_analyze_frame_teammates_unknown_without_minimap():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = np.full((1440, 2560, 3), 5, np.uint8)

    assert analyze_frame(frame, profile, t=0.0).dead_teammates is None


def _region_templates(profile):
    from lumia_briefing_room.detect.region import build_region_template, region_score

    roi = profile.rois["region_text"]
    rng = np.random.default_rng(7)
    ink = rng.random((roi.height, 40)) > 0.5
    patch = np.full((roi.height, roi.width, 3), 20, np.uint8)
    patch[6:26, 8:48][ink[6:26]] = 255
    return {"묘지": build_region_template([region_score(patch)])}, patch


def _frame_with_minimap(profile, *, alive=False):
    frame = np.full((1440, 2560, 3), 20, np.uint8)
    header = profile.rois["minimap_icons"]
    frame[header.y0 + 20 : header.y0 + 45, header.x0 : header.x1] = 210
    if alive:
        strip = profile.rois["hp_strip"]
        frame[strip.y0 + 80 : strip.y0 + 95, strip.x0 : strip.x0 + 200] = (90, 220, 40)
    return frame


def test_analyze_frame_reads_region_name():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    templates, patch = _region_templates(profile)
    frame = _frame_with_minimap(profile, alive=True)
    roi = profile.rois["region_text"]
    frame[roi.y0 : roi.y1, roi.x0 : roi.x1] = patch

    state = analyze_frame(frame, profile, t=0.0, region_templates=templates)

    assert state.region == "묘지"


def test_analyze_frame_region_is_none_without_templates():
    profile = ResolutionProfile.for_resolution(2560, 1440)

    assert analyze_frame(_frame_with_minimap(profile, alive=True), profile, t=0.0).region is None


def test_analyze_frame_skips_region_while_spectating():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    templates, patch = _region_templates(profile)
    frame = _frame_with_minimap(profile)
    roi = profile.rois["region_text"]
    frame[roi.y0 : roi.y1, roi.x0 : roi.x1] = patch

    state = analyze_frame(frame, profile, t=0.0, region_templates=templates)

    assert state.spectating is True
    assert state.region is None


def _region_state(t, combat, region, spectating=False):
    return FrameState(
        t=t, combat=combat, face_value=111.0, face_sat=26.0, k=0, a=0,
        day_night="day", spectating=spectating, region=region,
    )


def test_finalize_match_takes_the_first_region_seen_in_the_interval():
    states = [
        _region_state(0.0, False, "학교"),
        _region_state(3.0, True, None), _region_state(6.0, True, "묘지"),
        _region_state(9.0, True, "성당"), _region_state(12.0, False, "성당"),
    ]

    assert finalize_match(states).intervals[0].region == "묘지"


def test_finalize_match_region_is_none_when_never_read():
    states = [_region_state(0.0, False, None), _region_state(3.0, True, None), _region_state(6.0, True, None)]

    assert finalize_match(states).intervals[0].region is None


def _ring_state(t, combat, rings, spectating=False):
    return FrameState(
        t=t, combat=combat, face_value=111.0, face_sat=26.0, k=0, a=0,
        day_night="day", spectating=spectating, enemy_rings=rings,
    )


def test_finalize_match_averages_enemy_rings_over_the_interval():
    states = [
        _ring_state(0.0, False, 0), _ring_state(3.0, True, 2),
        _ring_state(6.0, True, 0), _ring_state(9.0, True, 1), _ring_state(12.0, False, 5),
    ]

    interval = finalize_match(states).intervals[0]

    assert interval.enemy_ring_mean == 1.0


def test_finalize_match_enemy_rings_skip_unread_and_spectating_samples():
    states = [
        _ring_state(0.0, False, 0), _ring_state(3.0, True, 3),
        _ring_state(6.0, True, None), _ring_state(9.0, True, 1), _ring_state(12.0, False, 0),
    ]

    assert finalize_match(states).intervals[0].enemy_ring_mean == 2.0


def test_finalize_match_enemy_ring_mean_is_none_when_never_read():
    states = [_ring_state(0.0, False, None), _ring_state(3.0, True, None), _ring_state(6.0, True, None)]

    assert finalize_match(states).intervals[0].enemy_ring_mean is None


def _ultimate_state(t, combat, ultimate_blue, spectating=False, locked=False):
    return FrameState(
        t=t, combat=combat, face_value=111.0, face_sat=26.0, k=0, a=0,
        day_night="day", spectating=spectating, ultimate_blue=ultimate_blue,
        ultimate_locked=locked,
    )


def test_finalize_match_ultimate_delta_is_the_spread_seen_around_the_interval():
    # 실측(134809_01): 준비 0.0 -> 쿨타임 진입 0.48 -> 되돌아옴. 교전 구간 자체는
    # 짧아도 앞뒤(UNCOVERED_EVENT_LOOKBACK_SEC)를 같이 봐서 델타를 놓치지 않는다.
    states = [
        _ultimate_state(0.0, False, 0.0),
        _ultimate_state(3.0, True, 0.40),
        _ultimate_state(6.0, True, 0.48),
        _ultimate_state(9.0, False, 0.30),
    ]

    interval = finalize_match(states).intervals[0]

    assert interval.ultimate_delta == 0.48


def test_finalize_match_ultimate_delta_skips_unread_samples():
    states = [
        _ultimate_state(0.0, False, 0.10),
        _ultimate_state(3.0, True, None),
        _ultimate_state(6.0, True, None),
        _ultimate_state(9.0, False, 0.20),
    ]

    interval = finalize_match(states).intervals[0]

    assert interval.ultimate_delta == pytest.approx(0.10)


def test_finalize_match_ultimate_delta_is_none_when_never_read():
    states = [
        _ultimate_state(0.0, False, None),
        _ultimate_state(3.0, True, None),
        _ultimate_state(6.0, True, None),
        _ultimate_state(9.0, False, None),
    ]

    assert finalize_match(states).intervals[0].ultimate_delta is None


def test_finalize_match_excludes_locked_icon_frames_from_the_ultimate_delta():
    # 2026-09-23 실사용 오탐: 스킬 레벨업으로 아이콘이 "잠김"(어두움) -> "해금"(원래 색)
    # 으로 바뀌는 순간이 blue_tint_ratio 델타를 밀어올려 궁 사용으로 오판됐다. 잠김
    # 프레임은 최솟값/최댓값 계산에서 아예 빼야 한다.
    states = [
        _ultimate_state(0.0, False, 0.0, locked=True),  # 잠김 - 기준선에서 제외돼야 함
        _ultimate_state(3.0, True, 0.55, locked=False),  # 해금 직후, 원화 자체가 파랗다
        _ultimate_state(6.0, True, 0.58, locked=False),
        _ultimate_state(9.0, False, 0.56, locked=False),
    ]

    interval = finalize_match(states).intervals[0]

    # 잠김 프레임(0.0)이 최솟값으로 잡히면 델타가 0.58 이 되어 오탐이 난다.
    # 제외하면 해금 상태끼리의 진폭(0.55~0.58)만 남아 델타가 훨씬 작다.
    assert interval.ultimate_delta == pytest.approx(0.03)


def test_finalize_match_ultimate_delta_is_none_when_every_frame_is_locked():
    states = [
        _ultimate_state(0.0, False, 0.0, locked=True),
        _ultimate_state(3.0, True, 0.1, locked=True),
        _ultimate_state(6.0, True, 0.05, locked=True),
    ]

    assert finalize_match(states).intervals[0].ultimate_delta is None


def test_analyze_frame_counts_enemy_rings_on_the_minimap_while_alive():
    import cv2

    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = _frame_with_minimap(profile, alive=True)
    roi = profile.rois["minimap"]
    for dx, dy in ((80, 80), (200, 120)):
        cx, cy = roi.x0 + dx, roi.y0 + dy
        cv2.circle(frame, (cx, cy), 12, (8, 8, 8), -1)
        cv2.circle(frame, (cx, cy), 12, (230, 40, 40), 3)

    assert analyze_frame(frame, profile, t=0.0).enemy_rings == 2


def test_analyze_frame_skips_minimap_while_spectating():
    profile = ResolutionProfile.for_resolution(2560, 1440)

    assert analyze_frame(_frame_with_minimap(profile), profile, t=0.0).enemy_rings is None


def _paint_ultimate(frame, profile, rgb):
    roi = profile.rois["ultimate_r"]
    frame[roi.y0 : roi.y1, roi.x0 : roi.x1] = rgb


def test_analyze_frame_reads_ultimate_blue_tint_when_alive():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = _frame_with_minimap(profile, alive=True)
    _paint_ultimate(frame, profile, (40, 90, 180))  # 쿨타임 오버레이 색

    assert analyze_frame(frame, profile, t=0.0).ultimate_blue == 1.0


def test_analyze_frame_ultimate_blue_is_none_while_spectating():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = _frame_with_minimap(profile)  # alive=False -> 관전
    _paint_ultimate(frame, profile, (40, 90, 180))

    state = analyze_frame(frame, profile, t=0.0)
    assert state.spectating is True
    assert state.ultimate_blue is None


def test_analyze_frame_ultimate_blue_is_none_without_the_roi():
    # 1920x1080 프로필은 아직 ultimate_r ROI 가 없다(2026-09-22 기준) - 우아하게 건너뛴다.
    profile = ResolutionProfile.for_resolution(1920, 1080)
    assert "ultimate_r" not in profile.rois
    frame = np.full((1080, 1920, 3), 20, np.uint8)

    assert analyze_frame(frame, profile, t=0.0).ultimate_blue is None


def test_analyze_frame_reads_ultimate_locked_when_alive():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = _frame_with_minimap(profile, alive=True)
    roi = profile.rois["ultimate_r"]
    _paint_ultimate(frame, profile, (40, 40, 40))
    red_rows = max(1, round(roi.height * 0.055))
    frame[roi.y0 : roi.y0 + red_rows, roi.x0 : roi.x1] = (200, 20, 20)  # 잠김 X 오버레이 비율만큼 빨갛게

    assert analyze_frame(frame, profile, t=0.0).ultimate_locked is True


def test_analyze_frame_ultimate_locked_is_false_for_a_bright_unlocked_icon():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = _frame_with_minimap(profile, alive=True)
    _paint_ultimate(frame, profile, (200, 120, 40))  # 준비 상태 원화 색

    assert analyze_frame(frame, profile, t=0.0).ultimate_locked is False


def _day_templates(profile):
    from lumia_briefing_room.detect.day import white_score
    from lumia_briefing_room.detect.region import build_region_template

    roi = profile.rois["day_digit"]
    rng = np.random.default_rng(11)
    patch = np.full((roi.height, roi.width, 3), 20, np.uint8)
    ink = rng.random((14, 11)) > 0.5
    patch[6:20, 2:13][ink] = 255
    return {"4": build_region_template([white_score(patch)])}, patch


def test_analyze_frame_reads_game_day_from_the_top_hud():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    templates, patch = _day_templates(profile)
    frame = _frame_with_minimap(profile, alive=True)
    roi = profile.rois["day_digit"]
    frame[roi.y0 : roi.y1, roi.x0 : roi.x1] = patch

    state = analyze_frame(frame, profile, t=0.0, day_templates=templates)

    assert state.game_day == 4


def test_analyze_frame_reads_game_day_even_while_spectating():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    templates, patch = _day_templates(profile)
    frame = _frame_with_minimap(profile)
    roi = profile.rois["day_digit"]
    frame[roi.y0 : roi.y1, roi.x0 : roi.x1] = patch

    state = analyze_frame(frame, profile, t=0.0, day_templates=templates)

    assert state.spectating is True
    assert state.game_day == 4


def test_analyze_frame_game_day_is_none_without_hud_or_templates():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    templates, patch = _day_templates(profile)
    blank = np.full((1440, 2560, 3), 5, np.uint8)

    assert analyze_frame(blank, profile, t=0.0, day_templates=templates).game_day is None
    assert analyze_frame(_frame_with_minimap(profile, alive=True), profile, t=0.0).game_day is None


def _phase_templates(profile):
    from lumia_briefing_room.detect.region import build_region_template, region_score

    roi = profile.rois["phase_digit"]
    rng = np.random.default_rng(13)
    patch = np.full((roi.height, roi.width, 3), 30, np.uint8)
    ink = rng.random((roi.height - 4, roi.width - 4)) > 0.5
    patch[2 : roi.height - 2, 2 : roi.width - 2][ink] = (200, 120, 40)
    return {"2": build_region_template([region_score(patch)])}, patch


def test_analyze_frame_reads_cobalt_phase_from_the_top_hud():
    profile = ResolutionProfile.for_resolution(1920, 1080)
    templates, patch = _phase_templates(profile)
    frame = _alive_frame(profile)
    roi = profile.rois["phase_digit"]
    frame[roi.y0 : roi.y1, roi.x0 : roi.x1] = patch

    state = analyze_frame(frame, profile, t=0.0, phase_templates=templates)

    assert state.cobalt_phase == 2


def test_analyze_frame_cobalt_phase_is_none_without_templates_or_roi():
    profile = ResolutionProfile.for_resolution(1920, 1080)
    templates, patch = _phase_templates(profile)
    frame = _alive_frame(profile)
    roi = profile.rois["phase_digit"]
    frame[roi.y0 : roi.y1, roi.x0 : roi.x1] = patch

    assert analyze_frame(frame, profile, t=0.0).cobalt_phase is None

    # 실측 코발트 ROI 가 없는 해상도를 흉내낸다 - 1920x1080·2560x1440 둘 다 이제
    # phase_digit 을 실측해 둬서(2026-09-28) 진짜 "ROI 없는" 빌트인 프로필이 없다.
    no_phase_profile = ResolutionProfile(
        width=2560, height=1440,
        rois={k: v for k, v in profile.rois.items() if k != "phase_digit"},
        measured=True,
    )
    assert "phase_digit" not in no_phase_profile.rois
    assert (
        analyze_frame(
            _alive_frame(no_phase_profile), no_phase_profile, t=0.0, phase_templates=templates
        ).cobalt_phase
        is None
    )


def _day_state(t, combat, day):
    return FrameState(
        t=t, combat=combat, face_value=111.0, face_sat=26.0, k=0, a=0,
        day_night="day", spectating=False, game_day=day,
    )


def test_finalize_match_uses_the_most_common_day_in_the_interval():
    states = [
        _day_state(0.0, False, 3), _day_state(3.0, True, 4), _day_state(6.0, True, 4),
        _day_state(9.0, True, None), _day_state(12.0, True, 5), _day_state(15.0, False, 5),
    ]

    assert finalize_match(states).intervals[0].game_day == 4


def test_finalize_match_game_day_is_none_when_never_read():
    states = [_day_state(0.0, False, None), _day_state(3.0, True, None), _day_state(6.0, True, None)]

    assert finalize_match(states).intervals[0].game_day is None


def _phase_state(t, combat, phase, *, dead=False):
    face = (34.0, 13.0) if dead else (111.0, 26.0)
    return FrameState(
        t=t, combat=combat, face_value=face[0], face_sat=face[1], k=0, a=0,
        day_night="day", spectating=False, cobalt_phase=phase,
    )


def test_finalize_match_uses_the_most_common_cobalt_phase_in_the_interval():
    """코발트는 배지가 아니라 사망 구간으로 구간을 나눈다(§10-13) - 여기서는 사망으로
    첫 구간의 경계를 만들어 그 구간 안 phase 최빈값이 맞는지 본다."""
    states = [
        _phase_state(0.0, False, 1), _phase_state(3.0, True, 2), _phase_state(6.0, True, 2),
        _phase_state(9.0, True, None), _phase_state(12.0, True, 3, dead=True), _phase_state(15.0, False, 3, dead=True),
        _phase_state(18.0, False, 4),
    ]

    assert finalize_match(states).intervals[0].cobalt_phase == 2


def test_finalize_match_cobalt_phase_is_none_when_never_read():
    states = [_phase_state(0.0, False, None), _phase_state(3.0, True, None), _phase_state(6.0, True, None)]

    assert finalize_match(states).intervals[0].cobalt_phase is None


def test_infer_game_mode_picks_battle_royale_when_day_reads_win():
    from lumia_briefing_room.detect.match import infer_game_mode

    states = [_day_state(0.0, True, 3), _day_state(1.0, True, 4), _phase_state(2.0, True, 1)]

    assert infer_game_mode(states) == "battle_royale"


def test_infer_game_mode_picks_cobalt_when_phase_reads_win():
    from lumia_briefing_room.detect.match import infer_game_mode

    states = [_phase_state(0.0, True, 0), _phase_state(1.0, True, 1), _day_state(2.0, True, 3)]

    assert infer_game_mode(states) == "cobalt"


def test_infer_game_mode_defaults_to_battle_royale_when_neither_reads():
    from lumia_briefing_room.detect.match import infer_game_mode

    assert infer_game_mode([_day_state(0.0, True, None), _day_state(1.0, True, None)]) == "battle_royale"


def test_finalize_match_reports_the_inferred_game_mode():
    states = [_phase_state(0.0, True, 0), _phase_state(1.0, True, 1), _phase_state(2.0, True, 1)]

    assert finalize_match(states).game_mode == "cobalt"


def test_finalize_match_game_mode_defaults_to_battle_royale_for_empty_states():
    assert finalize_match([]).game_mode == "battle_royale"


def _cobalt_state(t, *, dead=False, k=0, a=0):
    face = (34.0, 13.0) if dead else (111.0, 26.0)
    return FrameState(
        t=t, combat=None, face_value=face[0], face_sat=face[1], k=k, a=a,
        day_night=None, spectating=False, cobalt_phase=1,
    )


def _cobalt_state_with_mismatched_default_face(t, *, dead=False):
    """기본(배틀로얄) 자리 값은 절대 사망처럼 안 보이게 고정하고, 실제 사망 신호는
    cobalt_face_value/sat 에만 담는다 - finalize_match 가 기본 자리를 무시하고
    cobalt_face 를 쓰는지 가려낸다."""
    cobalt_face = (34.0, 13.0) if dead else (111.0, 26.0)
    return FrameState(
        t=t, combat=None, face_value=200.0, face_sat=5.0,
        cobalt_face_value=cobalt_face[0], cobalt_face_sat=cobalt_face[1],
        k=0, a=0, day_night=None, spectating=False, cobalt_phase=1,
    )


def test_finalize_match_cobalt_mode_prefers_cobalt_face_position_for_death_detection():
    """얼굴 ROI 는 코발트에서 배틀로얄과 다른 자리에 있다(실측, 코발트.mp4 2026-09-29) -
    game_mode==cobalt 로 밝혀진 뒤에는 cobalt_face_value/sat 로 사망을 판정해야 하고,
    (틀린 자리를 보는) 기본 face_value/sat 는 무시해야 한다."""
    times = [float(t) for t in range(0, 30, 2)]
    dead_ranges = [(10.0, 16.0)]
    is_dead = lambda t: any(a <= t <= b for a, b in dead_ranges)

    states = [_cobalt_state_with_mismatched_default_face(t, dead=is_dead(t)) for t in times]

    det = finalize_match(states)

    assert det.game_mode == "cobalt"
    assert len(det.intervals) == 2
    ivs = sorted(det.intervals, key=lambda iv: iv.start)
    assert ivs[0].died is True and ivs[0].end < 10.0
    assert ivs[1].start > 16.0


def test_finalize_match_cobalt_mode_treats_each_alive_span_as_one_interval():
    """사용자 결정(2026-09-28): 코발트는 야생동물도 없고 이동도 거의 없이 계속 교전의
    연속이라, 개별 킬/배지 이벤트로 잘게 쪼개는 대신 부활~다음 사망까지를 통째로 클립
    하나로 만든다 - 사망 중일 때만 클립 대상에서 뺀다."""
    times = [float(t) for t in range(0, 60, 2)]
    dead_ranges = [(14.0, 20.0), (40.0, 46.0)]
    is_dead = lambda t: any(a <= t <= b for a, b in dead_ranges)

    states = [_cobalt_state(t, dead=is_dead(t)) for t in times]

    det = finalize_match(states)

    assert det.game_mode == "cobalt"
    assert len(det.intervals) == 3
    ivs = sorted(det.intervals, key=lambda iv: iv.start)
    assert ivs[0].start == times[0] and ivs[0].end < 14.0
    assert 20.0 < ivs[1].start and ivs[1].end < 40.0
    assert 46.0 < ivs[2].start and ivs[2].end == times[-1]
    # 사망으로 끝난 구간엔 death 태그가 붙고, 게임이 그냥 끝나는 마지막 구간엔 안 붙는다.
    assert ivs[0].died is True and "death" in ivs[0].tags
    assert ivs[1].died is True and "death" in ivs[1].tags
    assert ivs[2].died is False


def test_finalize_match_cobalt_mode_still_tags_kills_and_assists_within_a_span():
    times = [float(t) for t in range(0, 20, 2)]
    k_values = {t: (1 if t >= 10 else 0) for t in times}
    a_values = {t: (1 if t >= 14 else 0) for t in times}
    states = [_cobalt_state(t, k=k_values[t], a=a_values[t]) for t in times]

    det = finalize_match(states)

    assert len(det.intervals) == 1
    iv = det.intervals[0]
    assert iv.k_delta == 1 and iv.a_delta == 1
    assert {"kill", "assist"} <= iv.tags


def test_finalize_match_battle_royale_mode_is_unaffected_by_the_cobalt_branch():
    """코발트 분기를 추가해도 배틀로얄(기존 배지·킬 이벤트 기반) 경로는 그대로여야 한다."""
    times = [0, 3, 6, 9, 12]
    combat_on = {3, 6, 9}
    states = [fs(t, t in combat_on) for t in times]

    det = finalize_match(states)

    assert det.game_mode == "battle_royale"
    assert len(det.intervals) == 1
    assert (det.intervals[0].start, det.intervals[0].end) == (3, 9)


def _team_frame(profile, *, ring_slot=None, dead_slot=None, alive=True):
    frame = _frame_with_minimap(profile, alive=alive)
    for slot in (1, 2):
        bar = profile.rois[f"team_bar{slot}"]
        frame[bar.y0 : bar.y1, bar.x0 : bar.x0 + 40] = (90, 220, 40)
    if ring_slot:
        ring = profile.rois[f"team_ring{ring_slot}"]
        frame[ring.y0 : ring.y1, ring.x0 : ring.x1] = (230, 40, 40)
    if dead_slot:
        bar = profile.rois[f"team_bar{dead_slot}"]
        frame[bar.y0 : bar.y1, bar.x0 : bar.x1] = (20, 20, 20)
        frame[bar.y0 : bar.y1, bar.x0 : bar.x0 + 10] = (240, 150, 30)
    return frame


def test_analyze_frame_reads_team_combat_from_a_red_teammate_ring():
    profile = ResolutionProfile.for_resolution(2560, 1440)

    assert analyze_frame(_team_frame(profile, ring_slot=2), profile, t=0.0).team_combat is True
    assert analyze_frame(_team_frame(profile), profile, t=0.0).team_combat is False


def test_analyze_frame_team_combat_ignores_a_dead_teammates_red_portrait():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = _team_frame(profile, ring_slot=1, dead_slot=1)

    assert analyze_frame(frame, profile, t=0.0).team_combat is False


def test_analyze_frame_team_combat_is_none_without_the_hud():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    blank = np.full((1440, 2560, 3), 5, np.uint8)

    assert analyze_frame(blank, profile, t=0.0).team_combat is None


def _tc_state(t, combat, team):
    return FrameState(
        t=t, combat=combat, face_value=111.0, face_sat=26.0, k=0, a=0,
        day_night="day", spectating=False, team_combat=team,
    )


def test_finalize_match_bridges_a_badge_gap_while_a_teammate_is_fighting():
    states = [_tc_state(0.0, False, False)]
    states += [_tc_state(3.0, True, False), _tc_state(6.0, True, False)]
    states += [_tc_state(9.0 + 3 * i, False, True) for i in range(8)]
    states += [_tc_state(33.0, True, True), _tc_state(36.0, True, True), _tc_state(39.0, False, False)]

    bridged = finalize_match(states).intervals
    badge_only = finalize_match(states, use_team_combat=False).intervals

    assert len(bridged) == 1 and bridged[0].end == 36.0
    assert len(badge_only) == 2


def test_finalize_match_keeps_a_fight_only_teammates_were_seen_in_because_missing_a_fight_costs_more_than_a_false_clip():
    states = [_tc_state(0.0, False, False), _tc_state(3.0, False, True), _tc_state(6.0, False, True),
              _tc_state(9.0, False, False)]

    intervals = finalize_match(states).intervals

    assert [(iv.start, iv.end) for iv in intervals] == [(3.0, 6.0)]
    assert intervals[0].confidence == 0.0


def test_finalize_match_team_combat_extends_an_interval_that_has_my_own_badge():
    states = [_tc_state(0.0, False, False), _tc_state(3.0, True, False), _tc_state(6.0, True, True),
              _tc_state(9.0, False, True), _tc_state(12.0, False, True), _tc_state(15.0, False, False)]

    interval = finalize_match(states).intervals[0]

    assert (interval.start, interval.end) == (3.0, 12.0)


def test_finalize_match_unread_team_state_does_not_hide_a_badge_reading():
    states = [_tc_state(0.0, False, None), _tc_state(3.0, True, None), _tc_state(6.0, True, None),
              _tc_state(9.0, False, None)]

    assert len(finalize_match(states).intervals) == 1


def _room_state(t, combat, region):
    return FrameState(
        t=t, combat=combat, face_value=111.0, face_sat=26.0, k=0, a=0,
        day_night="day", spectating=False, region=region,
    )


def test_finalize_match_ignores_the_pre_match_waiting_room():
    states = [_room_state(0.0, False, "브리핑 룸"), _room_state(3.0, True, "브리핑 룸"),
              _room_state(6.0, True, "브리핑 룸"), _room_state(9.0, False, "브리핑 룸")]

    assert finalize_match(states).intervals == []


def test_finalize_match_still_detects_fights_outside_the_waiting_room():
    states = [_room_state(0.0, False, "묘지"), _room_state(3.0, True, "묘지"),
              _room_state(6.0, True, "묘지"), _room_state(9.0, False, "묘지")]

    assert len(finalize_match(states).intervals) == 1


def _sp_state(t, combat, spectating):
    return FrameState(
        t=t, combat=None if spectating else combat, face_value=None if spectating else 111.0,
        face_sat=None if spectating else 26.0, k=None if spectating else 0, a=None if spectating else 0,
        day_night="day", spectating=spectating,
    )


def test_finalize_match_makes_a_clip_for_a_death_that_no_badge_interval_explains():
    states = [_sp_state(3.0 * i, False, False) for i in range(20)]
    states += [_sp_state(60.0, True, False), _sp_state(63.0, False, True), _sp_state(66.0, False, True),
               _sp_state(69.0, False, True)]

    intervals = finalize_match(states).intervals

    assert len(intervals) == 1
    assert intervals[0].died and "death" in intervals[0].tags
    assert intervals[0].start < 60.0 <= intervals[0].end < 63.0


def test_finalize_match_does_not_duplicate_a_death_already_inside_an_interval():
    states = [_sp_state(0.0, False, False)]
    states += [_sp_state(3.0 * i, True, False) for i in range(1, 6)]
    states += [_sp_state(18.0, False, True), _sp_state(21.0, False, True), _sp_state(24.0, False, True)]

    assert len(finalize_match(states).intervals) == 1


def _saturated_states(total=30):
    """팀원 신호가 계속 켜져 있는 경기: 배지는 t=30~36 한 번만 켜진다."""
    return [_tc_state(3.0 * i, 30.0 <= 3.0 * i <= 36.0, True) for i in range(total)]


def test_finalize_match_ignores_a_team_combat_signal_that_is_on_almost_all_game():
    intervals = finalize_match(_saturated_states()).intervals

    assert [(iv.start, iv.end) for iv in intervals] == [(30.0, 36.0)]


def test_finalize_match_flags_intervals_as_team_combat_unreliable_when_saturated():
    # 2026-09-23 실사용: 팀원의 커스텀 프로필 사진 속 빨간 요소가 "전투 중" 링 판정을
    # 매치 내내(샘플 30/30) 오탐시켰다. 포화 가드가 배지 전용으로 되돌리는 것과 별개로,
    # 이 매치의 구간들은 "배지만으로 잘랐다"는 표시를 남겨야 클립 자르기 단계에서
    # preroll 을 더 넉넉히 줄 수 있다(pipeline/clip.py resolve_clip_range).
    intervals = finalize_match(_saturated_states()).intervals

    assert intervals[0].team_combat_unreliable is True


def test_finalize_match_keeps_using_team_combat_when_it_is_only_on_now_and_then():
    states = [_tc_state(3.0 * i, False, 10 <= i < 14) for i in range(30)]

    intervals = finalize_match(states).intervals

    assert [(iv.start, iv.end) for iv in intervals] == [(30.0, 39.0)]
    assert intervals[0].team_combat_unreliable is False


def test_finalize_match_short_sequences_are_never_judged_saturated():
    states = [_tc_state(3.0 * i, False, True) for i in range(6)]

    assert len(finalize_match(states).intervals) == 1


def test_finalize_match_turns_a_kill_outside_the_badge_into_a_combat_interval():
    times = list(range(0, 90, 3))
    combat_on = {30, 33, 36}
    k_values = {t: (1 if t >= 60 else 0) for t in times}
    states = [fs(t, t in combat_on, k=k_values[t]) for t in times]

    result = finalize_match(states)

    kill = [i for i in result.intervals if "kill" in i.tags]
    assert len(kill) == 1
    assert kill[0].k_delta == 1
    assert kill[0].start <= 60 - 9 and kill[0].end >= 60


def test_finalize_match_merges_a_kill_interval_that_touches_a_badge_interval():
    times = list(range(0, 60, 3))
    combat_on = {18, 21, 24}
    k_values = {t: (1 if t >= 33 else 0) for t in times}
    states = [fs(t, t in combat_on, k=k_values[t]) for t in times]

    result = finalize_match(states)

    assert len(result.intervals) == 1
    assert result.intervals[0].start == 18
    assert result.intervals[0].tags == frozenset({"kill"})


def test_finalize_match_turns_an_assist_outside_the_badge_into_a_combat_interval():
    times = list(range(0, 60, 3))
    a_values = {t: (1 if t >= 30 else 0) for t in times}
    states = [fs(t, False, a=a_values[t]) for t in times]

    result = finalize_match(states)

    assert [i.tags for i in result.intervals] == [frozenset({"assist"})]


def test_analyze_frame_reads_badge_and_daynight_on_a_1080p_frame():
    profile = ResolutionProfile.for_resolution(1920, 1080)
    frame = _alive_frame(profile)
    _paint(frame, profile.rois["badge"], (255, 150, 20))
    _paint(frame, profile.rois["face"], (120, 100, 90))
    _paint(frame, profile.rois["day_night"], (255, 200, 20))

    state = analyze_frame(frame, profile, t=7.0)

    assert state.combat is True
    assert state.face_value == pytest.approx(120.0)
    assert state.day_night == "day"


class _CountingSource:
    """프레임을 몇 장 내줬는지 세는 가짜 소스. 취소가 프레임 사이에서 먹히는지 본다."""

    width, height = 2560, 1440

    def __init__(self, total: int):
        self.total = total
        self.yielded = 0

    def gaps(self):
        return []

    def frames(self):
        for n in range(self.total):
            self.yielded += 1
            yield n * 3.0, np.zeros((1440, 2560, 3), dtype=np.uint8)


def test_detect_source_stops_between_frames_when_cancelled():
    import threading

    from lumia_briefing_room.detect.match import DetectionCancelled, detect_source

    cancel = threading.Event()
    source = _CountingSource(total=50)
    original = source.frames

    def frames_and_cancel_at_five():
        for i, item in enumerate(original(), start=1):
            if i == 5:
                cancel.set()
            yield item

    source.frames = frames_and_cancel_at_five

    with pytest.raises(DetectionCancelled):
        detect_source(source, cancel=cancel)

    assert source.yielded < 50


def test_detect_source_without_cancel_reads_everything():
    from lumia_briefing_room.detect.match import detect_source

    source = _CountingSource(total=4)
    detect_source(source)
    assert source.yielded == 4
