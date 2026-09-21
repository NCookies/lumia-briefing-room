from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from lumia_briefing_room.detect.badge import read_badge
from lumia_briefing_room.detect.color import channel_stats
from lumia_briefing_room.detect.counter import (
    final_confirmed_value,
    load_templates,
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
from lumia_briefing_room.detect.region import load_region_templates, read_region, region_score
from lumia_briefing_room.detect.spectator import read_spectating
from lumia_briefing_room.detect.teammate import combat_slots, dead_slots, new_deaths
from lumia_briefing_room.detect.types import CombatInterval, FrameState, MatchDetection
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.segments import SegmentRange
from lumia_briefing_room.video.session import RecordingSession
from lumia_briefing_room.video.source import FrameSource, SteamSegmentSource

TAG_TOLERANCE_SEC = 3.0
WAITING_ROOM_REGIONS = frozenset({"브리핑 룸"})
DEATH_LINK_SEC = 8.0
UNEXPLAINED_DEATH_LOOKBACK_SEC = 12.0
UNCOVERED_EVENT_LOOKBACK_SEC = 12.0
MIN_SPECTATOR_SAMPLES = 2
TEAM_COMBAT_SATURATION = 0.6
MIN_TEAM_COMBAT_SAMPLES = 20

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


def analyze_frame(
    frame: np.ndarray,
    profile: ResolutionProfile,
    *,
    t: float,
    k_templates: dict[int, np.ndarray] | None = None,
    a_templates: dict[int, np.ndarray] | None = None,
    region_templates: dict[str, np.ndarray] | None = None,
    day_templates: dict[str, np.ndarray] | None = None,
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

    if spectating:
        combat = None
        face_value = face_sat = None
    else:
        combat = read_badge(profile.crop(frame, "badge"))
        face_stats = channel_stats(profile.crop(frame, "face"))
        face_value = float(face_stats.v.mean())
        face_sat = float(face_stats.s.mean())

    day_night = read_day_night(profile.crop(frame, "day_night"))

    region = None
    if region_templates and spectating is False:
        region = read_region(
            region_score(profile.crop(frame, "region_text")), region_templates
        ).name

    k_value = None
    if k_templates:
        k_crop = profile.crop(frame, "k_value")
        k_value = read_field(text_score(k_crop), k_templates).value

    a_value = None
    if a_templates:
        a_crop = profile.crop(frame, "a_value")
        a_value = read_field(text_score(a_crop), a_templates).value

    return FrameState(
        t=t,
        combat=combat,
        face_value=face_value,
        face_sat=face_sat,
        k=k_value,
        a=a_value,
        day_night=day_night,
        spectating=spectating,
        dead_teammates=dead_teammates,
        region=region,
        enemy_rings=enemy_rings,
        ally_rings=ally_rings,
        game_day=game_day,
        team_combat=team_combat,
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


def _mode(values: list[str]) -> str | None:
    if not values:
        return None
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts, key=counts.get)


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
    if use_team_combat and _team_combat_saturated(states):
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

    def _fighting(s: FrameState) -> bool | None:
        """내 배지 OR 팀원 전투. 배지는 구도를 잡거나 거리를 벌리는 동안 꺼지지만 팀원 링은 켜져 있다.

        브리핑 룸은 본게임 전 대기방이라 교전이 아니다.
        """
        if _spectating(s.t) or s.region in WAITING_ROOM_REGIONS:
            return False
        if s.combat is True or (use_team_combat and s.team_combat is True):
            return True
        if s.combat is None and (not use_team_combat or s.team_combat is None):
            return None
        return False

    combat_ranges = to_intervals([(s.t, _fighting(s)) for s in states])
    for sp_start, _ in spectator_ranges:
        if not any(_overlaps(a, b, sp_start, DEATH_LINK_SEC) for a, b in combat_ranges):
            first = states[0].t
            start = max(first, sp_start - UNEXPLAINED_DEATH_LOOKBACK_SEC)
            end = sp_start - states_step(states)
            if start <= end:
                combat_ranges.append((start, end))

    k_events = to_events([(s.t, s.k) for s in states], "K")
    a_events = to_events([(s.t, s.a) for s in states], "A")
    step = states_step(states)
    first = states[0].t
    for event in k_events + a_events:
        if event.delta > 0 and not any(_overlaps(a, b, event.t, tag_tolerance) for a, b in combat_ranges):
            combat_ranges.append((max(first, event.t - UNCOVERED_EVENT_LOOKBACK_SEC), event.t))
    combat_ranges = _merge_ranges(combat_ranges, step)

    face_stats = [
        FaceStat(t=s.t, value=s.face_value, sat=s.face_sat)
        for s in states
        if s.face_value is not None and s.face_sat is not None and not _spectating(s.t)
    ]
    death_ranges = detect_death(face_stats)

    teammate_deaths = new_deaths(
        [(s.t, list(s.dead_teammates)) for s in states if s.dead_teammates is not None]
    )

    intervals: list[CombatInterval] = []
    for start, end in combat_ranges:
        k_delta = sum(e.delta for e in k_events if _overlaps(start, end, e.t, tag_tolerance))
        a_delta = sum(e.delta for e in a_events if _overlaps(start, end, e.t, tag_tolerance))
        died = any(_intervals_overlap(start, end, d_start, d_end) for d_start, d_end in death_ranges)
        died = died or any(_overlaps(start, end, sp_start, DEATH_LINK_SEC) for sp_start, _ in spectator_ranges)

        team_deaths = sum(
            1 for t, _ in teammate_deaths if _overlaps(start, end, t, DEATH_LINK_SEC)
        )

        in_range = [s for s in states if start <= s.t <= end and not _spectating(s.t)]
        region = next((s.region for s in in_range if s.region), None)
        rings = [s.enemy_rings for s in in_range if s.enemy_rings is not None]
        enemy_ring_mean = sum(rings) / len(rings) if rings else None
        game_day = _mode([str(s.game_day) for s in in_range if s.game_day is not None])
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
            )
        )

    return MatchDetection(
        intervals=intervals, k_final=k_final, a_final=a_final,
        gaps=gaps, source_incomplete=bool(gaps),
        spectator_ranges=spectator_ranges, teammate_deaths=teammate_deaths,
    )


def detect_source(
    source: FrameSource,
    *,
    profile: ResolutionProfile | None = None,
    k_templates: dict[int, np.ndarray] | None = None,
    a_templates: dict[int, np.ndarray] | None = None,
) -> MatchDetection:
    """프레임 공급자 하나를 통째로 검출한다. 스팀 세그먼트든 영상 파일이든 같은 시계열 처리를 쓴다."""
    profile = profile or ResolutionProfile.for_resolution(source.width, source.height)
    k_templates, a_templates = resolve_templates(profile, k_templates, a_templates)
    region_templates = resolve_region_templates(profile)
    day_templates = resolve_day_templates(profile)

    states = [
        analyze_frame(
            frame, profile, t=t, k_templates=k_templates, a_templates=a_templates,
            region_templates=region_templates, day_templates=day_templates,
        )
        for t, frame in source.frames()
    ]
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
) -> MatchDetection:
    """매치 구간(세그먼트 범위) 하나를 통째로 검출한다. (plan.md §9-6)"""
    source = SteamSegmentSource(
        session, seg_range, stream=stream, ffmpeg_path=ffmpeg_path, hwaccel=hwaccel
    )
    return detect_source(
        source, profile=profile, k_templates=k_templates, a_templates=a_templates
    )
