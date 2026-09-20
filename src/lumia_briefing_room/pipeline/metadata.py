import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from lumia_briefing_room.config import dataclass_to_camel_dict
from lumia_briefing_room.detect.pvp import PvpScore
from lumia_briefing_room.detect.types import CombatInterval
from lumia_briefing_room.pipeline.clip import ClipRange, CutResult
from lumia_briefing_room.video.session import RecordingSession


def phase_index(game_day: int, day_night: str) -> int:
    """SPEC §2.0: 페이즈 순번. 1일차 낮=0, 1일차 밤=1, 2일차 낮=2, ..."""
    return (game_day - 1) * 2 + (0 if day_night == "day" else 1)


def revive_cost(phase: int) -> str:
    """SPEC §2.0: 2일차 밤까지(phase<=3) 무료, 3일차 낮부터(phase>=4) 크레딧."""
    return "free" if phase <= 3 else "credit"


def _isoformat_z(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ClipMetadata:
    """SPEC §3 클립 메타데이터 스키마 그대로."""

    title: str
    session_dir: str
    session_start_utc: str
    match_start_utc: str
    game_mode: str
    source_width: int
    source_height: int
    segment_start: int
    segment_end: int
    video_offset_sec: float
    duration_sec: float
    thumbnail_path: str | None
    source_incomplete: bool
    audio_status: str
    combat_start_offset_sec: float
    combat_end_offset_sec: float
    preroll_source: str
    tags: list[str]
    kill_delta: int
    assist_delta: int
    died: bool
    pvp_score: float
    pvp_signals: list[str]
    team_wipe: str | None
    enemy_ring_mean: float | None
    region: str | None
    user_label: str | None
    game_day: int | None
    day_night: str | None
    phase_index: int | None
    revive_cost: str | None
    my_character: str | None
    team_characters: list[str]
    pinned: bool
    deleted_at: str | None
    match_kills: int | None
    match_assists: int | None
    match_team_kills: int | None
    detector_confidence: float


def build_metadata(
    *,
    title: str,
    session: RecordingSession,
    match_start_utc: datetime,
    game_mode: str,
    interval: CombatInterval,
    clip_range: ClipRange,
    cut_result: CutResult,
    thumbnail_path: str | None,
    pvp: PvpScore | None = None,
    game_day: int | None = None,
    my_character: str | None = None,
    team_characters: list[str] | None = None,
    match_kills: int | None = None,
    match_assists: int | None = None,
    match_team_kills: int | None = None,
) -> ClipMetadata:
    day_night = interval.day_night
    phase = phase_index(game_day, day_night) if game_day is not None and day_night is not None else None

    return ClipMetadata(
        title=title,
        session_dir=session.directory.name,
        session_start_utc=_isoformat_z(session.start_utc),
        match_start_utc=_isoformat_z(match_start_utc),
        game_mode=game_mode,
        source_width=session.width,
        source_height=session.height,
        segment_start=cut_result.segment_start,
        segment_end=cut_result.segment_end,
        video_offset_sec=clip_range.start,
        duration_sec=cut_result.duration_sec,
        thumbnail_path=thumbnail_path,
        source_incomplete=cut_result.source_incomplete,
        audio_status=cut_result.audio_status,
        combat_start_offset_sec=interval.start,
        combat_end_offset_sec=interval.end,
        preroll_source=clip_range.preroll_source,
        tags=sorted(interval.tags),
        kill_delta=interval.k_delta,
        assist_delta=interval.a_delta,
        died=interval.died,
        pvp_score=pvp.score if pvp else 0.0,
        pvp_signals=list(pvp.signals) if pvp else [],
        team_wipe=None,
        enemy_ring_mean=interval.enemy_ring_mean,
        region=interval.region,
        user_label=None,
        game_day=game_day,
        day_night=day_night,
        phase_index=phase,
        revive_cost=revive_cost(phase) if phase is not None else None,
        my_character=my_character,
        team_characters=team_characters or [],
        pinned=False,
        deleted_at=None,
        match_kills=match_kills,
        match_assists=match_assists,
        match_team_kills=match_team_kills,
        detector_confidence=interval.confidence,
    )


def write_metadata(meta: ClipMetadata, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(dataclass_to_camel_dict(meta), ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
