from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from lumia_briefing_room.config import ClipConfig, Config, resolve_paths
from lumia_briefing_room.detect.match import detect_match
from lumia_briefing_room.detect.types import CombatInterval
from lumia_briefing_room.pipeline.clip import ClipRange, cut_clip, make_thumbnail, resolve_clip_range
from lumia_briefing_room.pipeline.filters import apply_filter
from lumia_briefing_room.pipeline.metadata import build_metadata, write_metadata
from lumia_briefing_room.video.segments import segment_time_range
from lumia_briefing_room.video.session import RecordingSession

_DAY_NIGHT_KR = {"day": "낮", "night": "밤"}


def default_title(day_night: str | None) -> str:
    """SPEC §7.7 titleTemplate 의 축소판.

    일차/캐릭터 인식이 아직 없어(plan.md §8-5, v2 후보) 낮/밤만 반영한다.
    """
    return f"{_DAY_NIGHT_KR.get(day_night, '알 수 없음')} 교전"


def _aggregate_interval(intervals: list[CombatInterval]) -> CombatInterval:
    """겹치거나 가까워 한 클립으로 합쳐진 교전들의 태그/수치를 하나로 모은다."""
    tags: frozenset[str] = frozenset()
    for iv in intervals:
        tags = tags | iv.tags
    return CombatInterval(
        start=intervals[0].start,
        end=intervals[-1].end,
        tags=tags,
        k_delta=sum(iv.k_delta for iv in intervals),
        a_delta=sum(iv.a_delta for iv in intervals),
        died=any(iv.died for iv in intervals),
        day_night=intervals[0].day_night,
        confidence=min(iv.confidence for iv in intervals),
        teammate_deaths=sum(iv.teammate_deaths for iv in intervals),
        region=next((iv.region for iv in intervals if iv.region), None),
    )


@dataclass(frozen=True)
class ClipPlan:
    range: ClipRange
    intervals: list[CombatInterval]


def _plan_clips(intervals: list[CombatInterval], cfg: ClipConfig) -> list[ClipPlan]:
    """SPEC §3: 교전마다 구간을 정하고, 겹치거나 mergeGapSec 이내면 하나로 합친다."""
    if not intervals:
        return []

    pairs = sorted(
        ((resolve_clip_range(iv, cfg), iv) for iv in intervals),
        key=lambda pair: pair[0].start,
    )

    plans: list[ClipPlan] = [ClipPlan(range=pairs[0][0], intervals=[pairs[0][1]])]
    for r, iv in pairs[1:]:
        last = plans[-1]
        if r.start <= last.range.end + cfg.merge_gap_sec:
            merged_range = ClipRange(
                start=last.range.start,
                end=max(last.range.end, r.end),
                preroll_source=last.range.preroll_source,
            )
            plans[-1] = ClipPlan(range=merged_range, intervals=last.intervals + [iv])
        else:
            plans.append(ClipPlan(range=r, intervals=[iv]))
    return plans


def _resolve_clip_paths(cfg: Config, clips_dir: Path | None) -> tuple[Path, Path]:
    """clips_dir 를 오버라이드해도 썸네일이 그 아래(`.thumbs`)를 따라가게 한다.

    resolve_paths(cfg.paths) 만 쓰면 cfg.paths.clips(설정 파일 기본 경로) 기준으로
    고정돼, 호출자가 clips_dir 인자로 다른 위치를 지정해도 무시된다 — 실제
    녹화본으로 처음 돌려봤을 때 썸네일이 지정한 곳이 아니라 기본 경로에
    생기는 것으로 발견한 버그다.
    """
    resolved = resolve_paths(cfg.paths)
    clips_root = clips_dir or resolved.clips
    thumbnails_root = cfg.paths.thumbnails or (clips_root / ".thumbs")
    return clips_root, thumbnails_root


def process_match(
    session: RecordingSession,
    match_start: datetime,
    match_end: datetime,
    cfg: Config,
    *,
    ffmpeg_path: Path,
    game_mode: str = "battle_royale",
    k_templates: dict[int, np.ndarray] | None = None,
    a_templates: dict[int, np.ndarray] | None = None,
    clips_dir: Path | None = None,
    hwaccel: str | None = None,
) -> list[Path]:
    """SPEC §3 다이어그램 전체: 매치 하나를 검출부터 메타데이터 저장까지 처리한다.

    반환값은 만들어진 메타데이터 JSON 경로 목록이다(클립 0개면 빈 리스트).
    """
    seg_range = segment_time_range(session, match_start, match_end)
    detection = detect_match(
        session, seg_range, ffmpeg_path=ffmpeg_path,
        k_templates=k_templates, a_templates=a_templates, hwaccel=hwaccel,
    )

    filtered = apply_filter(detection.intervals, cfg.filter, game_mode=game_mode)
    if not filtered:
        return []

    resolved = resolve_paths(cfg.paths)
    clips_root, thumbnails_root = _resolve_clip_paths(cfg, clips_dir)
    clips_root.mkdir(parents=True, exist_ok=True)
    resolved.temp.mkdir(parents=True, exist_ok=True)

    plans = _plan_clips(filtered, cfg.clip)

    written: list[Path] = []
    for i, plan in enumerate(plans, start=1):
        aggregated = _aggregate_interval(plan.intervals)
        clip_id = f"{match_start:%Y%m%d_%H%M%S}_{i:02d}"
        clip_path = clips_root / f"{clip_id}.mp4"

        cut_result = cut_clip(
            session, plan.range, clip_path,
            ffmpeg_path=ffmpeg_path, include_audio=cfg.clip.include_audio,
            tmp_dir=resolved.temp,
        )

        thumbnail_rel: str | None = None
        if cfg.encode.thumbnail.enabled:
            thumb_path = thumbnails_root / f"{clip_id}.jpg"
            make_thumbnail(
                clip_path, thumb_path,
                duration_sec=cut_result.duration_sec,
                offset_ratio=cfg.encode.thumbnail.offset_ratio,
                width=cfg.encode.thumbnail.width,
                ffmpeg_path=ffmpeg_path,
            )
            thumbnail_rel = str(thumb_path)

        meta = build_metadata(
            title=default_title(aggregated.day_night),
            session=session,
            match_start_utc=match_start,
            game_mode=game_mode,
            interval=aggregated,
            clip_range=plan.range,
            cut_result=cut_result,
            thumbnail_path=thumbnail_rel,
            match_kills=detection.k_final,
            match_assists=detection.a_final,
        )
        meta_path = clip_path.with_suffix(".json")
        write_metadata(meta, meta_path)
        written.append(meta_path)

    return written
