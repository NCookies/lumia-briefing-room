from __future__ import annotations

from pathlib import Path

import numpy as np

from lumia_briefing_room.detect.badge import read_badge
from lumia_briefing_room.detect.color import channel_stats
from lumia_briefing_room.detect.counter import final_confirmed_value, read_field, to_events
from lumia_briefing_room.detect.daynight import read_day_night
from lumia_briefing_room.detect.death import FaceStat, detect_death
from lumia_briefing_room.detect.glyph import text_score
from lumia_briefing_room.detect.intervals import to_intervals
from lumia_briefing_room.detect.types import CombatInterval, FrameState, MatchDetection
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.frames import crop_roi, extract_keyframe_frames
from lumia_briefing_room.video.segments import SegmentRange, existing_segment_numbers
from lumia_briefing_room.video.session import RecordingSession

TAG_TOLERANCE_SEC = 3.0


def analyze_frame(
    frame: np.ndarray,
    profile: ResolutionProfile,
    *,
    t: float,
    k_templates: dict[int, np.ndarray] | None = None,
    a_templates: dict[int, np.ndarray] | None = None,
) -> FrameState:
    """프레임 하나에서 교전/사망/카운터/낮밤 신호를 전부 읽는다. (plan.md §5)"""
    combat = read_badge(crop_roi(frame, profile.rois["badge"]))

    face_stats = channel_stats(crop_roi(frame, profile.rois["face"]))
    face_value = float(face_stats.v.mean())
    face_sat = float(face_stats.s.mean())

    day_night = read_day_night(crop_roi(frame, profile.rois["day_night"]))

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
    )


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

    combat_ranges = to_intervals([(s.t, s.combat) for s in states])

    face_stats = [
        FaceStat(t=s.t, value=s.face_value, sat=s.face_sat)
        for s in states
        if s.face_value is not None and s.face_sat is not None
    ]
    death_ranges = detect_death(face_stats)

    k_events = to_events([(s.t, s.k) for s in states], "K")
    a_events = to_events([(s.t, s.a) for s in states], "A")

    intervals: list[CombatInterval] = []
    for start, end in combat_ranges:
        k_delta = sum(e.delta for e in k_events if _overlaps(start, end, e.t, tag_tolerance))
        a_delta = sum(e.delta for e in a_events if _overlaps(start, end, e.t, tag_tolerance))
        died = any(_intervals_overlap(start, end, d_start, d_end) for d_start, d_end in death_ranges)

        in_range = [s for s in states if start <= s.t <= end]
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
        if not tags:
            tags.add("no_result")

        intervals.append(
            CombatInterval(
                start=start, end=end, tags=frozenset(tags),
                k_delta=k_delta, a_delta=a_delta, died=died,
                day_night=day_night, confidence=confidence,
            )
        )

    return MatchDetection(
        intervals=intervals, k_final=k_final, a_final=a_final,
        gaps=gaps, source_incomplete=bool(gaps),
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
            analyze_frame(frame, profile, t=t, k_templates=k_templates, a_templates=a_templates)
        )

    return finalize_match(states, gaps=gaps)
