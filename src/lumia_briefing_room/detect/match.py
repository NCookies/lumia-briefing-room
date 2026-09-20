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
)
from lumia_briefing_room.detect.daynight import read_day_night
from lumia_briefing_room.detect.death import FaceStat, detect_death
from lumia_briefing_room.detect.glyph import text_score
from lumia_briefing_room.detect.intervals import to_intervals
from lumia_briefing_room.detect.region import load_region_templates, read_region, region_score
from lumia_briefing_room.detect.spectator import read_spectating
from lumia_briefing_room.detect.teammate import dead_slots, new_deaths
from lumia_briefing_room.detect.types import CombatInterval, FrameState, MatchDetection
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.frames import crop_roi, extract_keyframe_frames
from lumia_briefing_room.video.segments import SegmentRange, existing_segment_numbers
from lumia_briefing_room.video.session import RecordingSession

TAG_TOLERANCE_SEC = 3.0
DEATH_LINK_SEC = 8.0
MIN_SPECTATOR_SAMPLES = 2

log = logging.getLogger(__name__)


def resolve_templates(
    profile: ResolutionProfile,
    k_templates: dict[int, np.ndarray] | None,
    a_templates: dict[int, np.ndarray] | None,
) -> tuple[dict[int, np.ndarray] | None, dict[int, np.ndarray] | None]:
    if k_templates is not None and a_templates is not None:
        return k_templates, a_templates

    loaded = load_templates(profile.templates) if profile.templates else None
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
) -> FrameState:
    """프레임 하나에서 교전/사망/카운터/낮밤 신호를 전부 읽는다. (plan.md §5)"""
    spectating = read_spectating(
        crop_roi(frame, profile.rois["minimap_icons"]),
        crop_roi(frame, profile.rois["hp_strip"]),
    )

    dead_teammates = None
    if spectating is not None:
        dead_teammates = tuple(
            dead_slots(
                [
                    crop_roi(frame, profile.rois["team_bar1"]),
                    crop_roi(frame, profile.rois["team_bar2"]),
                ]
            )
        )

    if spectating:
        combat = None
        face_value = face_sat = None
    else:
        combat = read_badge(crop_roi(frame, profile.rois["badge"]))
        face_stats = channel_stats(crop_roi(frame, profile.rois["face"]))
        face_value = float(face_stats.v.mean())
        face_sat = float(face_stats.s.mean())

    day_night = read_day_night(crop_roi(frame, profile.rois["day_night"]))

    region = None
    if region_templates and spectating is False:
        region = read_region(
            region_score(crop_roi(frame, profile.rois["region_text"])), region_templates
        ).name

    k_value = None
    if k_templates:
        k_crop = crop_roi(frame, profile.rois["k_value"])
        k_value = read_field(text_score(k_crop), k_templates).value

    a_value = None
    if a_templates:
        a_crop = crop_roi(frame, profile.rois["a_value"])
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
    )


def resolve_region_templates(profile: ResolutionProfile) -> dict[str, np.ndarray] | None:
    if profile.region_templates is None:
        log.warning(
            "지역명 템플릿을 찾을 수 없다(%dx%d) - 클립 제목에 지역이 빠진다",
            profile.width, profile.height,
        )
        return None
    return load_region_templates(profile.region_templates)


def _overlaps(start: float, end: float, t: float, tolerance: float) -> bool:
    return start - tolerance <= t <= end + tolerance


def _intervals_overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return a_start <= b_end and a_end >= b_start


def _mode(values: list[str]) -> str | None:
    if not values:
        return None
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts, key=counts.get)


def finalize_match(
    states: list[FrameState],
    *,
    gaps: list[tuple[float, float]] | None = None,
    tag_tolerance: float = TAG_TOLERANCE_SEC,
) -> MatchDetection:
    """프레임별 판독을 교전 구간 + 태그로 합친다. (plan.md §3, §5.3~5.6)"""
    gaps = gaps or []

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

    combat_ranges = to_intervals(
        [(s.t, False if _spectating(s.t) else s.combat) for s in states]
    )

    face_stats = [
        FaceStat(t=s.t, value=s.face_value, sat=s.face_sat)
        for s in states
        if s.face_value is not None and s.face_sat is not None and not _spectating(s.t)
    ]
    death_ranges = detect_death(face_stats)

    teammate_deaths = new_deaths(
        [(s.t, list(s.dead_teammates)) for s in states if s.dead_teammates is not None]
    )

    k_events = to_events([(s.t, s.k) for s in states], "K")
    a_events = to_events([(s.t, s.a) for s in states], "A")

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
            )
        )

    return MatchDetection(
        intervals=intervals, k_final=k_final, a_final=a_final,
        gaps=gaps, source_incomplete=bool(gaps),
        spectator_ranges=spectator_ranges, teammate_deaths=teammate_deaths,
    )


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
    profile = profile or ResolutionProfile.for_resolution(session.width, session.height)
    k_templates, a_templates = resolve_templates(profile, k_templates, a_templates)
    region_templates = resolve_region_templates(profile)

    existing = existing_segment_numbers(session, stream, seg_range.first, seg_range.last)
    gap_segments = seg_range.gaps(existing)
    duration = session.segment_duration_sec
    gaps = [
        ((g0 - 1) * duration, g1 * duration) for g0, g1 in gap_segments
    ]

    states: list[FrameState] = []
    for seg_num, frame in extract_keyframe_frames(
        session, stream=stream, segment_numbers=existing,
        ffmpeg_path=ffmpeg_path, hwaccel=hwaccel,
    ):
        t = (seg_num - 1) * duration
        states.append(
            analyze_frame(
                frame, profile, t=t, k_templates=k_templates, a_templates=a_templates,
                region_templates=region_templates,
            )
        )

    return finalize_match(states, gaps=gaps)
