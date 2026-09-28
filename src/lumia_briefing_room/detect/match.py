from __future__ import annotations

import dataclasses
import itertools
import logging
import threading
from pathlib import Path

import cv2
import numpy as np

from lumia_briefing_room.detect.badge import read_badge
from lumia_briefing_room.detect.clock import read_clock_zero
from lumia_briefing_room.detect.color import channel_stats
from lumia_briefing_room.detect.counter import (
    final_confirmed_value,
    load_templates,
    locate_digit,
    read_field,
    to_events,
    with_two_digit_templates,
)
from lumia_briefing_room.detect.day import read_game_day
from lumia_briefing_room.detect.daynight import read_day_night
from lumia_briefing_room.detect.death import FaceStat, detect_death
from lumia_briefing_room.detect.glyph import text_score
from lumia_briefing_room.detect.intervals import to_intervals
from lumia_briefing_room.detect.minimap import count_rings
from lumia_briefing_room.detect.phase import read_cobalt_phase
from lumia_briefing_room.detect.region import load_region_templates, read_region, region_score
from lumia_briefing_room.detect.spectator import read_spectating
from lumia_briefing_room.detect.teammate import combat_slots, dead_slots, new_deaths
from lumia_briefing_room.detect.ultimate import blue_tint_ratio, is_locked, max_rise
from lumia_briefing_room.detect.types import CombatInterval, FrameState, MatchDetection
from lumia_briefing_room.profiles.models import ResolutionProfile, Roi
from lumia_briefing_room.video.segments import SegmentRange
from lumia_briefing_room.video.session import RecordingSession
from lumia_briefing_room.video.source import FrameSource, SteamSegmentSource

TAG_TOLERANCE_SEC = 3.0
WAITING_ROOM_REGIONS = frozenset({"브리핑 룸"})
DEATH_LINK_SEC = 8.0
UNEXPLAINED_DEATH_LOOKBACK_SEC = 12.0
UNCOVERED_EVENT_LOOKBACK_SEC = 12.0
# 궁극기 델타(detect/ultimate.py)는 짧은 교전 구간 안에서 "준비" 기준선을 못 볼 수 있어
# 앞뒤를 더 넓게 본다. ClipConfig 기본값(preroll_sec=5, postroll_sec=8)을 넘기면 안 된다 -
# 넘기면 메타데이터의 "궁극기 사용" 근거가 실제 컷 클립 밖(안 보이는 구간)에서 읽힌 값이
# 되어 사용자가 클립을 봐도 그 장면이 없는 버그가 난다(2026-09-23 실사용 보고로 발견).
ULTIMATE_LOOKBACK_SEC = 5.0
ULTIMATE_LOOKFORWARD_SEC = 8.0
# 배지가 꺼진 뒤 곧 결착(킬/어시/팀킬)이 나면 구간 끝을 그 시점까지 늘린다(2026-09-23
# 실사용 보고: VOD 1일차 낮 교전 · 마르티나, 배지 꺼지고 2초 뒤 팀원이 막타). TK 를
# 여기 쓰는 건 UNCOVERED_EVENT_LOOKBACK_SEC 과 달리 안전하다 - 이미 있는 구간의 끝만
# 늘릴 뿐 새 구간을 만들지 않는다.
TRAILING_KILL_EXTEND_SEC = 12.0
MIN_SPECTATOR_SAMPLES = 2
MIN_WAITING_SAMPLES = 5
TEAM_COMBAT_SATURATION = 0.6
MIN_TEAM_COMBAT_SAMPLES = 20
# 코발트 TK/K/A 폴백 위치의 판독 문턱(§10-8) - 실측(코발트.mp4, 6게임 시작 시점의
# TK=K=A=0 + 중간 지점 실측값)으로 정답이 최소 0.014 마진까지 내려가는 걸 확인해
# counter.py 기본값(0.05)보다 낮춰 잡는다.
COBALT_COUNTER_MIN_MARGIN = 0.01

log = logging.getLogger(__name__)


def resolve_templates(
    profile: ResolutionProfile,
    k_templates: dict[int, np.ndarray] | None,
    a_templates: dict[int, np.ndarray] | None,
) -> tuple[dict[int, np.ndarray] | None, dict[int, np.ndarray] | None]:
    if k_templates is not None and a_templates is not None:
        return k_templates, a_templates

    loaded = with_two_digit_templates(load_templates(profile.templates)) if profile.templates else None
    if loaded is None:
        log.warning(
            "숫자 템플릿을 찾을 수 없다(%dx%d) - kill/assist 태그가 비어서 나온다",
            profile.width, profile.height,
        )
    return (
        k_templates if k_templates is not None else loaded,
        a_templates if a_templates is not None else loaded,
    )


def resolve_tk_templates(
    profile: ResolutionProfile,
    k_templates: dict[int, np.ndarray] | None,
) -> dict[int, np.ndarray] | None:
    """TK(팀 킬) 칸은 K/A 와 같은 폰트·같은 검정 HUD 배경이지만 필드 폭이 좁다(2026-09-23 실측).

    R 아이콘 쿨타임 숫자와 달리 배경이 균일해 새 표본 없이 K 템플릿을 필드 크기로
    리사이즈하는 것만으로 재사용된다(실측: 신뢰도 0.6대로 정확히 읽힘).

    크기는 `profile.rois`(이 프로필 자체의 실측값)가 아니라 `profile.crop()`이 실제로
    내놓는 크기를 써야 한다 - 정규화 프로필은 `crop()`이 기준 해상도 ROI 크기로 자동
    확대하므로(profiles/models.py), 템플릿도 그 기준 크기에 맞춰야 한다. 안 맞추면
    `read_field`가 크기 불일치로 조용히 None 만 낸다(2026-09-23 VOD 실측으로 발견).
    """
    if not k_templates or "tk_value" not in profile.rois:
        return None
    roi = (profile.reference_rois or profile.rois).get("tk_value")
    if roi is None:
        return None
    resized = {
        d: cv2.resize(t, (roi.width, roi.height), interpolation=cv2.INTER_LINEAR)
        for d, t in k_templates.items()
    }
    return with_two_digit_templates(resized)


def _crop_for_reference(profile: ResolutionProfile, frame: np.ndarray, roi_name: str, reference_like: str) -> np.ndarray:
    """`roi_name` 자리를 잘라 `reference_like`(예: k_value)의 기준 해상도 크기로 맞춘다.

    코발트 위치 ROI(cobalt_k_value 등)는 기준 해상도(2560x1440) 녹화가 없어(§10-1 관례와
    동일하게) `reference_rois` 표에 없다 - 본보기는 배틀로얄 자리 기준(기준 해상도)으로
    만들어졌으므로, `profile.crop()`이 하는 자동 확대를 여기서도 그대로 해 줘야 한다.
    """
    roi = profile.rois[roi_name]
    piece = frame[roi.y0 : roi.y1, roi.x0 : roi.x1]
    ref = profile.reference_rois.get(reference_like) if profile.reference_rois else None
    if ref is None or piece.shape[:2] == (ref.height, ref.width):
        return piece
    return cv2.resize(piece, (ref.width, ref.height), interpolation=cv2.INTER_CUBIC)


CALIBRATION_SAMPLE_FRAMES = 8
CALIBRATION_MIN_HITS = 3
CALIBRATION_MARGIN_X = 160
CALIBRATION_MARGIN_Y = 24
CALIBRATION_MIN_SCORE = 0.6


def _reference_scale(profile: ResolutionProfile, roi_name: str) -> tuple[float, float]:
    """이 ROI 를 기준 해상도로 키울 때 쓰는 배율(정규화 프로필이 아니거나 이 ROI 가
    기준 표에 없으면 1.0)."""
    roi = profile.rois[roi_name]
    ref = profile.reference_rois.get(roi_name) if profile.reference_rois else None
    if ref is None:
        return 1.0, 1.0
    return ref.width / roi.width, ref.height / roi.height


def calibrate_counter_position(
    profile: ResolutionProfile,
    frames: list[np.ndarray],
    k_templates: dict[int, np.ndarray],
) -> ResolutionProfile:
    """`k_value` 기본 자리에서 숫자가 안 읽히면, 그 주변 넓은 영역에서 실제 위치를
    찾아 `k_value`/`a_value`/`tk_value` 를 통째로 옮긴 프로필을 새로 만든다. (plan.md §10-13)

    실사용 보고(2026-09-28): 같은 해상도(1920x1080)인데도 영상마다 이 칸 위치가 달랐다
    (스트리머 VOD 의 코발트 vs 배틀로얄 — 사람이 실측해 보니 화면 배치 자체가 달랐다).
    매번 새 영상마다 좌표를 실측해 하드코딩하는 대신, 영상 처음 몇 프레임에서 기본 자리가
    안 맞으면 자동으로 찾는다. 세 칸이 같은 줄에 나란히 있다는 전제로 K 하나만 찾아 세
    칸을 같이 옮긴다 - 이 게임의 HUD 는 TK/K/A 가 항상 붙어 있어(§3) 따로 찾을 이유가
    없다.
    """
    k_roi = profile.rois["k_value"]
    sx, sy = _reference_scale(profile, "k_value")
    native_templates = {
        d: cv2.resize(t, (max(1, round(t.shape[1] / sx)), max(1, round(t.shape[0] / sy))), interpolation=cv2.INTER_AREA)
        if (sx, sy) != (1.0, 1.0)
        else t
        for d, t in k_templates.items()
    }

    x0 = max(0, k_roi.x0 - CALIBRATION_MARGIN_X)
    y0 = max(0, k_roi.y0 - CALIBRATION_MARGIN_Y)
    x1_want = k_roi.x1 + CALIBRATION_MARGIN_X
    y1_want = k_roi.y1 + CALIBRATION_MARGIN_Y

    found: list[tuple[int, int]] = []
    for frame in frames:
        # k_value 는 화면 오른쪽 끝에 붙어 있어 여유(margin)를 더하면 화면 밖으로
        # 나갈 수 있다 - 통째로 건너뛰지 않고 프레임 크기에 맞춰 자른다.
        x1 = min(frame.shape[1], x1_want)
        y1 = min(frame.shape[0], y1_want)
        if x1 <= x0 or y1 <= y0:
            continue
        region = frame[y0:y1, x0:x1]
        hit = locate_digit(text_score(region), native_templates, min_score=CALIBRATION_MIN_SCORE)
        if hit is not None:
            fx, fy, _digit, _score = hit
            found.append((x0 + fx, y0 + fy))

    if len(found) < CALIBRATION_MIN_HITS:
        return profile

    xs = sorted(p[0] for p in found)
    ys = sorted(p[1] for p in found)
    new_x0 = xs[len(xs) // 2]
    new_y0 = ys[len(ys) // 2]
    dx = new_x0 - k_roi.x0
    dy = new_y0 - k_roi.y0
    if dx == 0 and dy == 0:
        return profile

    shifted = dict(profile.rois)
    for name in ("k_value", "a_value", "tk_value"):
        if name not in profile.rois:
            continue
        r = profile.rois[name]
        shifted[name] = Roi(r.x0 + dx, r.y0 + dy, r.x1 + dx, r.y1 + dy)

    log.info("카운터 칸 위치를 자동으로 다시 찾았다: k_value 기준 (%+d,%+d)px", dx, dy)
    return dataclasses.replace(profile, rois=shifted)


def analyze_frame(
    frame: np.ndarray,
    profile: ResolutionProfile,
    *,
    t: float,
    k_templates: dict[int, np.ndarray] | None = None,
    a_templates: dict[int, np.ndarray] | None = None,
    tk_templates: dict[int, np.ndarray] | None = None,
    region_templates: dict[str, np.ndarray] | None = None,
    day_templates: dict[str, np.ndarray] | None = None,
    phase_templates: dict[str, np.ndarray] | None = None,
) -> FrameState:
    """프레임 하나에서 교전/사망/카운터/낮밤 신호를 전부 읽는다. (plan.md §5)"""
    spectating = read_spectating(
        profile.crop(frame, "minimap_icons"),
        profile.crop(frame, "hp_strip"),
    )

    dead_teammates = None
    team_combat = None
    if spectating is not None:
        team_combat = bool(
            combat_slots(
                [
                    profile.crop(frame, "team_ring1"),
                    profile.crop(frame, "team_ring2"),
                ],
                [
                    profile.crop(frame, "team_bar1"),
                    profile.crop(frame, "team_bar2"),
                ],
            )
        )
        dead_teammates = tuple(
            dead_slots(
                [
                    profile.crop(frame, "team_bar1"),
                    profile.crop(frame, "team_bar2"),
                ]
            )
        )

    game_day = None
    if day_templates and spectating is not None:
        game_day = read_game_day(profile.crop(frame, "day_digit"), day_templates)

    enemy_rings = ally_rings = None
    if spectating is False:
        counts = count_rings(profile.crop(frame, "minimap"))
        enemy_rings, ally_rings = counts.enemy, counts.ally

    if spectating is not False:
        # spectating 이 None 이면 미니맵조차 안 보인다는 뜻 - 관전(True)뿐 아니라 로딩·
        # 캐릭터 선택·로비 화면도 여기 해당한다(§2.12, read_spectating 참고). 이런 화면엔
        # 캐릭터 UI 자체가 없어 초상화 ROI 를 읽어도 의미가 없는데, 로딩 화면의 암전 전환이
        # 사망 램프와 비슷하게 보여 죽음으로 오판되는 사고가 있었다(2026-09-23, 캐릭터 선택
        # 화면이 "알 수 없음 교전"으로 잘못 뽑힌 사례). combat=False(확인됨)일 때만 읽는다.
        combat = None
        face_value = face_sat = None
    else:
        combat = read_badge(profile.crop(frame, "badge"))
        face_stats = channel_stats(profile.crop(frame, "face"))
        face_value = float(face_stats.v.mean())
        face_sat = float(face_stats.s.mean())

    day_night = read_day_night(profile.crop(frame, "day_night"))
    clock_zero = read_clock_zero(profile.crop(frame, "timer")) if "timer" in profile.rois else None

    ultimate_blue = None
    ultimate_locked = None
    if "ultimate_r" in profile.rois and spectating is False:
        ultimate_crop = profile.crop(frame, "ultimate_r")
        ultimate_blue = blue_tint_ratio(ultimate_crop)
        ultimate_locked = is_locked(ultimate_crop)

    region = None
    if region_templates and spectating is False:
        region = read_region(
            region_score(profile.crop(frame, "region_text")), region_templates
        ).name

    # 코발트 프로토콜은 같은 스트리머의 배틀로얄 녹화와 비교해 TK/K/A 칸이 화면에서
    # ~80px 왼쪽·3px 위에 렌더링된다(실측, 2026-09-27 - 두 모드를 같은 방송에서 프레임
    # 단위로 대조해 확인, plan.md §10-3·§10-8 후속). 게임 모드는 프레임 하나만 봐서는
    # 아직 모르므로(infer_game_mode 는 states 전체를 모아야 판정한다), 배틀로얄 위치를
    # 먼저 읽고 실패하면(다른 모드라 그 자리에 숫자가 없으면) 코발트 위치를 다시 읽는다.
    # 폰트와 필드 폭이 같아 본보기는 그대로 재사용한다. 코발트 자리는 네이티브 해상도
    # 크롭을 기준 해상도로 확대해서 비교하는 만큼 배틀로얄 원본보다 정보가 적어 1·2등
    # 후보 점수차(margin)가 좁다(실측: 정답이어도 0.01~0.08) - 배틀로얄 경로의 기본
    # 문턱(0.05)을 그대로 쓰면 정답도 대부분 버려져 `COBALT_COUNTER_MIN_MARGIN` 을
    # 따로 낮춰 쓴다.
    k_value = None
    if k_templates:
        k_value = read_field(text_score(profile.crop(frame, "k_value")), k_templates).value
        if k_value is None and "cobalt_k_value" in profile.rois:
            crop = _crop_for_reference(profile, frame, "cobalt_k_value", "k_value")
            k_value = read_field(text_score(crop), k_templates, min_margin=COBALT_COUNTER_MIN_MARGIN).value

    a_value = None
    if a_templates:
        a_value = read_field(text_score(profile.crop(frame, "a_value")), a_templates).value
        if a_value is None and "cobalt_a_value" in profile.rois:
            crop = _crop_for_reference(profile, frame, "cobalt_a_value", "a_value")
            a_value = read_field(text_score(crop), a_templates, min_margin=COBALT_COUNTER_MIN_MARGIN).value

    tk_value = None
    if tk_templates and "tk_value" in profile.rois:
        tk_value = read_field(text_score(profile.crop(frame, "tk_value")), tk_templates).value
        if tk_value is None and "cobalt_tk_value" in profile.rois:
            crop = _crop_for_reference(profile, frame, "cobalt_tk_value", "tk_value")
            tk_value = read_field(text_score(crop), tk_templates, min_margin=COBALT_COUNTER_MIN_MARGIN).value

    cobalt_phase = None
    if phase_templates and "phase_digit" in profile.rois:
        cobalt_phase = read_cobalt_phase(profile.crop(frame, "phase_digit"), phase_templates)

    return FrameState(
        t=t,
        combat=combat,
        face_value=face_value,
        face_sat=face_sat,
        k=k_value,
        a=a_value,
        tk=tk_value,
        day_night=day_night,
        spectating=spectating,
        dead_teammates=dead_teammates,
        region=region,
        enemy_rings=enemy_rings,
        ally_rings=ally_rings,
        game_day=game_day,
        team_combat=team_combat,
        clock_zero=clock_zero,
        ultimate_blue=ultimate_blue,
        ultimate_locked=ultimate_locked,
        cobalt_phase=cobalt_phase,
    )


def resolve_region_templates(profile: ResolutionProfile) -> dict[str, np.ndarray] | None:
    if profile.region_templates is None:
        log.warning(
            "지역명 템플릿을 찾을 수 없다(%dx%d) - 클립 제목에 지역이 빠진다",
            profile.width, profile.height,
        )
        return None
    return load_region_templates(profile.region_templates)


def resolve_day_templates(profile: ResolutionProfile) -> dict[str, np.ndarray] | None:
    if profile.day_templates is None:
        log.warning(
            "일차 템플릿을 찾을 수 없다(%dx%d) - 클립 제목에 일차가 빠진다",
            profile.width, profile.height,
        )
        return None
    return load_region_templates(profile.day_templates)


def resolve_phase_templates(profile: ResolutionProfile) -> dict[str, np.ndarray] | None:
    """plan.md §10-1: 코발트 프로토콜 전용, 기준 해상도가 아니라 프로필 자신의 본보기를 쓴다."""
    if profile.phase_templates is None:
        return None
    return load_region_templates(profile.phase_templates)


def states_step(states: list[FrameState]) -> float:
    return states[1].t - states[0].t if len(states) > 1 else 3.0


def _overlaps(start: float, end: float, t: float, tolerance: float) -> bool:
    return start - tolerance <= t <= end + tolerance


def _intervals_overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return a_start <= b_end and a_end >= b_start


def _merge_ranges(ranges: list[tuple[float, float]], gap: float) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _invert_ranges(ranges: list[tuple[float, float]], start: float, end: float) -> list[tuple[float, float]]:
    """`ranges`(이미 합쳐진 구간들) 로 덮이지 않은 나머지를 [start, end] 안에서 낸다.

    코발트 프로토콜의 "부활~사망" 구간(§10-13)을 만드는 데 쓴다 - 사망 구간의 여집합이
    곧 "교전 대상" 구간이다.
    """
    result: list[tuple[float, float]] = []
    cursor = start
    for a, b in sorted(ranges):
        if a > cursor:
            result.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < end:
        result.append((cursor, end))
    return result


def _mode(values: list[str]) -> str | None:
    if not values:
        return None
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts, key=counts.get)


def infer_game_mode(states: list[FrameState]) -> str:
    """SPEC §2.9 / plan.md §10 C1-b: 코발트는 `Phase N`, 배틀로얄은 `N일 차` 를 상단에 쓴다.

    HUD 나머지는 두 모드가 같아(§2.9) 둘 중 어느 판독이 더 많이 성공했는지 세는 것이
    가장 직접적인 신호다. 둘 다 못 읽으면(로비만 있거나 프로필이 없는 등) 기존 기본값을 유지한다.
    """
    cobalt_hits = sum(1 for s in states if s.cobalt_phase is not None)
    day_hits = sum(1 for s in states if s.game_day is not None)
    return "cobalt" if cobalt_hits > day_hits else "battle_royale"


def _team_combat_saturated(states: list[FrameState]) -> bool:
    """팀원 링 판독이 망가지면(링 색이 바뀌거나 팀원이 접속 불안정 등) 경기 내내 True 가 되어, 전투가 끝나지 않는 거대한 교전 구간 하나가 생긴다.

    정상 경기에서 이 신호는 10~15% 정도만 켜진다(실측). 대부분의 프레임에서 켜져 있으면 신호 자체를 버린다.
    """
    seen = [s.team_combat for s in states if s.team_combat is not None]
    return len(seen) >= MIN_TEAM_COMBAT_SAMPLES and sum(seen) / len(seen) > TEAM_COMBAT_SATURATION


def finalize_match(
    states: list[FrameState],
    *,
    gaps: list[tuple[float, float]] | None = None,
    tag_tolerance: float = TAG_TOLERANCE_SEC,
    use_team_combat: bool = True,
) -> MatchDetection:
    """프레임별 판독을 교전 구간 + 태그로 합친다. (plan.md §3, §5.3~5.6)"""
    gaps = gaps or []
    team_combat_unreliable = use_team_combat and _team_combat_saturated(states)
    if team_combat_unreliable:
        log.warning("팀원 전투 신호가 경기 내내 켜져 있어 신뢰할 수 없다 - 내 배지만으로 교전을 나눈다")
        use_team_combat = False

    k_final = final_confirmed_value([(s.t, s.k) for s in states])
    a_final = final_confirmed_value([(s.t, s.a) for s in states])

    if not states:
        return MatchDetection(
            intervals=[], k_final=k_final, a_final=a_final,
            gaps=gaps, source_incomplete=bool(gaps),
        )

    spectator_ranges = to_intervals(
        [(s.t, s.spectating) for s in states],
        gap_fill_samples=1, min_combat_samples=MIN_SPECTATOR_SAMPLES,
    )

    def _spectating(t: float) -> bool:
        return any(a <= t <= b for a, b in spectator_ranges)

    # 경기 시작 직후 캐릭터 선택/팀 소개 화면(RANK GAME, 팀 01~08)은 미니맵 헤더 아이콘은 보이고
    # 체력바만 없어 "관전"으로 읽힌다(2026-09-24 실사용). 죽으려면 먼저 살아 있는(spectating=False)
    # 화면이 있어야 하므로, 그 전에 시작한 관전은 사망으로 보지 않는다.
    first_live = next((s.t for s in states if s.spectating is False), None)
    death_starts = [a for a, _ in spectator_ranges if first_live is not None and a > first_live]

    waiting_ranges = to_intervals(
        [(s.t, s.clock_zero) for s in states],
        gap_fill_samples=1, min_combat_samples=MIN_WAITING_SAMPLES,
    )

    def _waiting(t: float) -> bool:
        return any(a <= t <= b for a, b in waiting_ranges)

    def _fighting(s: FrameState) -> bool | None:
        """내 배지 OR 팀원 전투. 배지는 구도를 잡거나 거리를 벌리는 동안 꺼지지만 팀원 링은 켜져 있다.

        브리핑 룸은 본게임 전 대기방이라 교전이 아니다.
        """
        if _spectating(s.t) or s.region in WAITING_ROOM_REGIONS or _waiting(s.t):
            return False
        if s.combat is True or (use_team_combat and s.team_combat is True):
            return True
        if s.combat is None and (not use_team_combat or s.team_combat is None):
            return None
        return False

    step = states_step(states)
    first = states[0].t
    game_mode = infer_game_mode(states)

    face_stats = [
        FaceStat(t=s.t, value=s.face_value, sat=s.face_sat)
        for s in states
        if s.face_value is not None and s.face_sat is not None and not _spectating(s.t)
    ]
    death_ranges = detect_death(face_stats)

    k_events = to_events([(s.t, s.k) for s in states], "K")
    a_events = to_events([(s.t, s.a) for s in states], "A")
    tk_events = to_events([(s.t, s.tk) for s in states], "TK")

    if game_mode == "cobalt":
        # 사용자 결정(2026-09-28): 코발트는 야생동물도 없고 이동도 거의 없이 계속
        # 교전의 연속이라, 배지·킬 이벤트로 잘게 쪼개는 배틀로얄 방식 대신 "부활~다음
        # 사망"을 통째로 구간 하나로 삼는다 - 죽어 있는 동안만 클립 대상에서 뺀다.
        # 사망은 두 신호의 합집합으로 본다: 초상화가 어두워지는 순간(death_ranges,
        # detect_death)과, 그 뒤 실제 관전 화면으로 넘어가는 구간(스펙테이터 UI).
        death_spectator_ranges = [
            (a, b) for a, b in spectator_ranges if first_live is not None and a > first_live
        ]
        dead_ranges = _merge_ranges(death_ranges + death_spectator_ranges, step)
        last = states[-1].t
        raw_alive = _invert_ranges(dead_ranges, first, last)
        # 사망으로 확정된 마지막 샘플이 다음 구간에도, 부활로 확정된 첫 샘플이 이전
        # 구간에도 겹쳐 들어가지 않게 안쪽으로 한 칸(step)씩 민다 - 경기 시작(첫 구간의
        # 시작)·경기 종료(마지막 구간의 끝)는 앞뒤로 죽음이 없으니 그대로 둔다.
        combat_ranges = [
            (a if a == first else a + step, b if b == last else b - step)
            for a, b in raw_alive
        ]
        combat_ranges = [(a, b) for a, b in combat_ranges if a <= b]
    else:
        combat_ranges = to_intervals([(s.t, _fighting(s)) for s in states])
        for sp_start in death_starts:
            if not any(_overlaps(a, b, sp_start, DEATH_LINK_SEC) for a, b in combat_ranges):
                start = max(first, sp_start - UNEXPLAINED_DEATH_LOOKBACK_SEC)
                end = sp_start - step
                if start <= end:
                    combat_ranges.append((start, end))

        # TK 는 여기(구간을 새로 만드는 쪽)에 안 넣는다 - 팀 전체 킬이라 내가 없는 곳의
        # 팀원 킬까지 새 구간을 만들면 코발트 프로토콜처럼 TK 가 빨리 오르는 모드에서
        # 가짜 클립이 쏟아진다(SPEC §2.8). TK 는 아래에서 "이미 있는 구간의 끝만" 늘리는
        # 용도로만 쓴다.
        for event in k_events + a_events:
            if event.delta > 0 and not any(_overlaps(a, b, event.t, tag_tolerance) for a, b in combat_ranges):
                combat_ranges.append((max(first, event.t - UNCOVERED_EVENT_LOOKBACK_SEC), event.t))
        combat_ranges = _merge_ranges(combat_ranges, step)

        # 내 배지(또는 팀원 전투 링)가 꺼진 뒤에도 곧 결착이 나는 경우가 있다(2026-09-23
        # 실사용 보고: 배지 꺼지고 2초 뒤 팀원이 막타). 새 구간은 안 만들고, 이미 있는
        # 구간의 끝만 가까운 킬 이벤트까지 늘린다.
        combat_ranges = [
            (
                start,
                max([end] + [e.t for e in k_events + a_events + tk_events if e.delta > 0 and end < e.t <= end + TRAILING_KILL_EXTEND_SEC]),
            )
            for start, end in combat_ranges
        ]
        combat_ranges = _merge_ranges(combat_ranges, step)

    teammate_deaths = new_deaths(
        [(s.t, list(s.dead_teammates)) for s in states if s.dead_teammates is not None]
    )

    intervals: list[CombatInterval] = []
    for start, end in combat_ranges:
        k_delta = sum(e.delta for e in k_events if _overlaps(start, end, e.t, tag_tolerance))
        a_delta = sum(e.delta for e in a_events if _overlaps(start, end, e.t, tag_tolerance))
        died = any(_intervals_overlap(start, end, d_start, d_end) for d_start, d_end in death_ranges)
        died = died or any(_overlaps(start, end, sp_start, DEATH_LINK_SEC) for sp_start in death_starts)
        if game_mode == "cobalt":
            # 코발트 구간은 사망 프레임과 안 겹치게 끝을 한 칸 당겨놨다(§10-13 위) - 그래서
            # 위의 "겹치는지"가 아니라 "바로 다음이 사망인지"로 봐야 한다.
            died = died or any(0 <= d_start - end <= step * 2 for d_start, _ in death_ranges)

        team_deaths = sum(
            1 for t, _ in teammate_deaths if _overlaps(start, end, t, DEATH_LINK_SEC)
        )

        in_range = [s for s in states if start <= s.t <= end and not _spectating(s.t)]
        region = next((s.region for s in in_range if s.region), None)
        rings = [s.enemy_rings for s in in_range if s.enemy_rings is not None]
        enemy_ring_mean = sum(rings) / len(rings) if rings else None
        game_day = _mode([str(s.game_day) for s in in_range if s.game_day is not None])
        cobalt_phase = _mode([str(s.cobalt_phase) for s in in_range if s.cobalt_phase is not None])

        around = [
            s for s in states
            if start - ULTIMATE_LOOKBACK_SEC <= s.t <= end + ULTIMATE_LOOKFORWARD_SEC and not _spectating(s.t)
        ]
        ultimate_values = [
            s.ultimate_blue for s in around
            if s.ultimate_blue is not None and not s.ultimate_locked
        ]
        ultimate_delta = max_rise(ultimate_values) if ultimate_values else None
        day_night = _mode([s.day_night for s in in_range if s.day_night])
        solid = sum(1 for s in in_range if s.combat is True)
        confidence = solid / len(in_range) if in_range else 0.0

        tags: set[str] = set()
        if k_delta > 0:
            tags.add("kill")
        if a_delta > 0:
            tags.add("assist")
        if died:
            tags.add("death")
        if team_deaths:
            tags.add("teammate_death")
        if not tags:
            tags.add("no_result")

        intervals.append(
            CombatInterval(
                start=start, end=end, tags=frozenset(tags),
                k_delta=k_delta, a_delta=a_delta, died=died,
                day_night=day_night, confidence=confidence,
                teammate_deaths=team_deaths, region=region,
                enemy_ring_mean=enemy_ring_mean,
                game_day=int(game_day) if game_day is not None else None,
                ultimate_delta=ultimate_delta,
                team_combat_unreliable=team_combat_unreliable,
                cobalt_phase=int(cobalt_phase) if cobalt_phase is not None else None,
            )
        )

    return MatchDetection(
        intervals=intervals, k_final=k_final, a_final=a_final,
        gaps=gaps, source_incomplete=bool(gaps),
        spectator_ranges=spectator_ranges, teammate_deaths=teammate_deaths,
        game_mode=game_mode,
    )


class DetectionCancelled(Exception):
    """검출 도중 취소됐다. 프레임 사이에서만 멈추므로 반쯤 쓴 결과는 남지 않는다."""


def detect_source(
    source: FrameSource,
    *,
    profile: ResolutionProfile | None = None,
    k_templates: dict[int, np.ndarray] | None = None,
    a_templates: dict[int, np.ndarray] | None = None,
    cancel: threading.Event | None = None,
) -> MatchDetection:
    """프레임 공급자 하나를 통째로 검출한다. 스팀 세그먼트든 영상 파일이든 같은 시계열 처리를 쓴다."""
    profile = profile or ResolutionProfile.for_resolution(source.width, source.height)
    k_templates, a_templates = resolve_templates(profile, k_templates, a_templates)
    region_templates = resolve_region_templates(profile)
    day_templates = resolve_day_templates(profile)
    phase_templates = resolve_phase_templates(profile)

    states = []
    frames = source.frames()
    try:
        # 처음 몇 프레임으로 k_value 기본 자리가 이 영상에서도 맞는지 확인한다 - 안 맞으면
        # (실사용 보고 2026-09-28: 같은 해상도인데 영상마다 이 칸 위치가 달랐다) 그 주변을
        # 뒤져 실제 위치를 찾아 이 영상 전체에 적용한다(plan.md §10-13). 버퍼링한 프레임도
        # 그대로 분석에 쓴다 - source.frames() 는 한 번만 순회할 수 있어 버려지면 안 된다.
        buffered: list[tuple[float, np.ndarray]] = []
        if k_templates:
            for item in frames:
                buffered.append(item)
                if len(buffered) >= CALIBRATION_SAMPLE_FRAMES:
                    break
            hits = sum(
                1 for _, f in buffered
                if read_field(text_score(profile.crop(f, "k_value")), k_templates).value is not None
            )
            if hits < CALIBRATION_MIN_HITS:
                profile = calibrate_counter_position(profile, [f for _, f in buffered], k_templates)

        tk_templates = resolve_tk_templates(profile, k_templates)

        for t, frame in itertools.chain(buffered, frames):
            if cancel is not None and cancel.is_set():
                raise DetectionCancelled()
            states.append(
                analyze_frame(
                    frame, profile, t=t, k_templates=k_templates, a_templates=a_templates,
                    tk_templates=tk_templates, region_templates=region_templates, day_templates=day_templates,
                    phase_templates=phase_templates,
                )
            )
    finally:
        close = getattr(frames, "close", None)
        if close is not None:
            close()
    return finalize_match(states, gaps=source.gaps())


def detect_match(
    session: RecordingSession,
    seg_range: SegmentRange,
    *,
    stream: int = 0,
    ffmpeg_path: Path,
    profile: ResolutionProfile | None = None,
    k_templates: dict[int, np.ndarray] | None = None,
    a_templates: dict[int, np.ndarray] | None = None,
    hwaccel: str | None = None,
    cancel: threading.Event | None = None,
) -> MatchDetection:
    """매치 구간(세그먼트 범위) 하나를 통째로 검출한다. (plan.md §9-6)"""
    source = SteamSegmentSource(
        session, seg_range, stream=stream, ffmpeg_path=ffmpeg_path, hwaccel=hwaccel
    )
    return detect_source(
        source, profile=profile, k_templates=k_templates, a_templates=a_templates, cancel=cancel
    )
