import threading
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from lumia_briefing_room.config import ClipConfig, Config, resolve_paths
from lumia_briefing_room.detect.match import detect_match
from lumia_briefing_room.detect.pvp import score_interval
from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.detect.types import CombatInterval, MatchDetection
from lumia_briefing_room.pipeline.clip import ClipRange, cut_clip, make_thumbnail, resolve_clip_range
from lumia_briefing_room.detect.types import PortraitCrops
from lumia_briefing_room.pipeline.filters import apply_filter
from lumia_briefing_room.pipeline.metadata import build_metadata, write_metadata
from lumia_briefing_room.pipeline.clip_assets import stored_asset_path
from lumia_briefing_room.pipeline.cleanup_registry import registry as cleanup_preview_registry
from lumia_briefing_room.pipeline.portrait_scan import (
    PORTRAIT_SLOTS,
    find_match_portraits,
    portrait_image_name,
    save_portrait_image,
)
from lumia_briefing_room.pipeline.result_scan import (
    find_result_after,
    find_result_screen,
    result_image_name,
    save_result_image,
)
from lumia_briefing_room.video.segments import segment_number_at, segment_time_range
from lumia_briefing_room.video.session import RecordingSession

log = logging.getLogger(__name__)

_DAY_NIGHT_KR = {"day": "낮", "night": "밤"}


def default_title(
    day_night: str | None,
    region: str | None = None,
    game_day: int | None = None,
    characters: list[str] | None = None,
    cobalt_phase: int | None = None,
    clip_index: int | None = None,
) -> str:
    """SPEC §7.7 titleTemplate 의 축소판.

    일차/캐릭터 인식이 아직 없어(plan.md §8-5, v2 후보) 낮/밤과 지역만 반영한다.

    코발트 프로토콜은 낮/밤·일차 개념이 없어 `game_day`/`day_night` 가 항상 `None` 이라
    "알 수 없음 교전"이 됐다(실사용 보고, 2026-09-28) - 대신 이미 읽고 있는 Phase 번호를
    붙인다. `game_day` 가 있으면(배틀로얄) 그쪽을 우선한다 - 두 모드는 겹치지 않는다.

    `day_night` 는 프레임마다 모드와 무관하게 항상 읽는다(§2.7) - 코발트 화면에서
    우연히 뭔가 읽혀도("Phase 3 낮 교전" 실사용 보고, 2026-09-28) 코발트엔 낮/밤 자체가
    없으므로 `cobalt_phase` 가 있으면 절대 안 보여준다.

    §10-13 이후 코발트 한 게임에 클립이 여러 개(목숨마다 하나) 생기는데, 같은 Phase 에서
    두 번 죽으면 제목이 겹친다 - `clip_index`(그 게임 안에서 이 클립이 몇 번째인지)를
    주면 뒤에 "- N" 을 붙여 구분한다(사용자 요청, 2026-09-28).
    """
    parts = []
    if game_day is not None:
        parts.append(f"{game_day}일차")
        parts.append(_DAY_NIGHT_KR.get(day_night, "알 수 없음"))
    elif cobalt_phase is not None:
        parts.append(f"Phase {cobalt_phase}")
    else:
        parts.append(_DAY_NIGHT_KR.get(day_night, "알 수 없음"))
    if region:
        parts.append(region)
    parts.append("교전")
    title = " ".join(parts)
    if characters:
        title = f"{title} · {', '.join(characters)}"
    if cobalt_phase is not None and clip_index is not None:
        title = f"{title} - {clip_index}"
    return title


def _mean_of_known(values: list[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None


def _max_of_known(values: list[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return max(known) if known else None


def _aggregate_interval(intervals: list[CombatInterval]) -> CombatInterval:
    """겹치거나 가까워 한 클립으로 합쳐진 교전들의 태그/수치를 하나로 모은다."""
    tags: frozenset[str] = frozenset()
    for iv in intervals:
        tags = tags | iv.tags
    if len(tags) > 1:
        tags = tags - {"no_result"}
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
        game_day=next((iv.game_day for iv in intervals if iv.game_day is not None), None),
        enemy_ring_mean=_mean_of_known([iv.enemy_ring_mean for iv in intervals]),
        ultimate_delta=_max_of_known([iv.ultimate_delta for iv in intervals]),
        team_combat_unreliable=any(iv.team_combat_unreliable for iv in intervals),
        cobalt_phase=next((iv.cobalt_phase for iv in intervals if iv.cobalt_phase is not None), None),
    )


@dataclass(frozen=True)
class ClipPlan:
    range: ClipRange
    intervals: list[CombatInterval]


def next_phase_clip_index(counts: dict[int | None, int], cobalt_phase: int | None) -> int:
    """코발트 클립 제목의 "- N"은 게임 전체가 아니라 같은 Phase 안에서 몇 번째인지다.

    (사용자 보고, 2026-09-28 - "Phase 2 교전 - 3"처럼 게임 전체 순번이 붙어 있었다.)
    `counts` 는 호출자가 게임 하나 동안 들고 있는 누적 카운터이며, Phase 값이 바뀌면
    그 Phase 는 다시 1부터 시작한다.
    """
    counts[cobalt_phase] = counts.get(cobalt_phase, 0) + 1
    return counts[cobalt_phase]


def _plan_clips(intervals: list[CombatInterval], cfg: ClipConfig, *, game_mode: str = "battle_royale") -> list[ClipPlan]:
    """SPEC §3: 교전마다 구간을 정하고, 겹치거나 mergeGapSec 이내면 하나로 합친다."""
    if not intervals:
        return []

    pairs = sorted(
        ((resolve_clip_range(iv, cfg, game_mode=game_mode), iv) for iv in intervals),
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


def _read_result(
    session, seg_range, ffmpeg_path: Path, hwaccel: str | None, *, search_from: datetime | None = None
) -> ResultScreen | None:
    """결과 화면 판독은 부가 정보라 실패해도 클립 생성을 막지 않는다.

    로그 기반 경기는 끝이 로비 복귀 시각이라 구간 끝에서 거슬러 오른다. 화면으로 찾은 경기(과거 녹화 복구)는 끝을 '마지막 인게임
    프레임'으로 알 뿐이라 `search_from`(그 시각) 뒤에서 앞으로 훑는다 — 구간 끝(다음 경기 시작 전)까지만 본다.
    """
    try:
        if search_from is not None:
            return find_result_after(
                session, segment_number_at(session, search_from),
                ffmpeg_path=ffmpeg_path, hwaccel=hwaccel, before_segment=seg_range.last + 1,
            )
        return find_result_screen(session, seg_range, ffmpeg_path=ffmpeg_path, hwaccel=hwaccel)
    except Exception:
        log.exception("결과 화면 판독 실패 - 순위 정보 없이 저장한다")
        return None


def _save_result_image(result: ResultScreen | None, path: Path, clips_root: Path) -> str | None:
    if result is None or result.image is None:
        return None
    try:
        save_result_image(result.image, path)
    except OSError:
        log.exception("결과 화면 이미지 저장 실패")
        return None
    return stored_asset_path(path, clips_root)


# 게임 하나를 처리하는 동안 각 단계가 차지하는 비중(plan-backfill.md B8 §7 확인 필요 3번 답).
# 실측(2026-09-28, H:\steam video 실제 21분 경기, 클립 12개): 검출(detect_match) 24.8초,
# 결과 화면 판독(find_result_after) 8.8초, 클립 컷·썸네일·메타데이터 21.6초, 전체 55.2초.
# 경기 길이·클립 수에 따라 비율이 달라질 수 있어 고정값이지만(다른 경기로 검증 못함), 진행 막대가
# 60~100초 동안 멈춘 듯 보이던 문제보다는 낫다.
DETECTION_PROGRESS_FRACTION = 0.45
RESULT_SCAN_PROGRESS_FRACTION = 0.61


def _find_portraits(
    session: RecordingSession, seg_range, ffmpeg_path: Path, hwaccel: str | None
) -> PortraitCrops | None:
    """초상화 판독은 부가 정보라 실패해도 클립 생성을 막지 않는다."""
    try:
        return find_match_portraits(session, seg_range, ffmpeg_path=ffmpeg_path, hwaccel=hwaccel)
    except Exception:
        log.exception("팀 소개 화면 초상화 판독 실패 - 초상화 없이 저장한다")
        return None


def _save_portrait_images(
    portraits: PortraitCrops | None, match_start: datetime, thumbnails_root: Path, clips_root: Path
) -> dict[str, str | None]:
    paths: dict[str, str | None] = {slot: None for slot in PORTRAIT_SLOTS}
    if portraits is None:
        return paths
    for slot in PORTRAIT_SLOTS:
        path = thumbnails_root / portrait_image_name(match_start, slot)
        try:
            save_portrait_image(getattr(portraits, slot), path)
        except OSError:
            log.exception("초상화 이미지 저장 실패(%s)", slot)
            continue
        paths[slot] = stored_asset_path(path, clips_root)
    return paths


def process_match(
    session: RecordingSession,
    match_start: datetime,
    match_end: datetime,
    cfg: Config,
    *,
    ffmpeg_path: Path,
    game_mode: str | None = None,
    k_templates: dict[int, np.ndarray] | None = None,
    a_templates: dict[int, np.ndarray] | None = None,
    clips_dir: Path | None = None,
    hwaccel: str | None = None,
    on_result: Callable[[ResultScreen], None] | None = None,
    cancel: threading.Event | None = None,
    result_search_from: datetime | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> list[Path]:
    """SPEC §3 다이어그램 전체: 매치 하나를 검출부터 메타데이터 저장까지 처리한다.

    `game_mode` 를 안 주면(기본) 검출 결과(`Phase N` vs `N일 차` 판독 횟수, plan.md §10
    C1-b)로 자동 판별한다. 명시하면(CLI `--game-mode` 등) 그 값을 그대로 쓴다.

    반환값은 만들어진 메타데이터 JSON 경로 목록이다(클립 0개면 빈 리스트).
    `on_progress(0~1)` 는 이 게임 하나의 내부 진행률이다(plan-backfill B8) — 검출 프레임 비율 →
    결과 화면 판독 → 클립마다 컷·썸네일 순으로 올라간다.
    """
    seg_range = segment_time_range(session, match_start, match_end)

    def _frame_progress(done: int, total: int | None) -> None:
        if on_progress is not None and total:
            on_progress(min(1.0, done / total) * DETECTION_PROGRESS_FRACTION)

    detection: MatchDetection = detect_match(
        session, seg_range, ffmpeg_path=ffmpeg_path,
        k_templates=k_templates, a_templates=a_templates, hwaccel=hwaccel, cancel=cancel,
        on_progress=_frame_progress if on_progress is not None else None,
    )
    game_mode = game_mode if game_mode is not None else detection.game_mode

    filtered = apply_filter(detection.intervals, cfg.filter, game_mode=game_mode)
    if not filtered:
        if on_progress is not None:
            on_progress(1.0)
        return []

    if on_progress is not None:
        on_progress(DETECTION_PROGRESS_FRACTION)

    resolved = resolve_paths(cfg.paths)
    clips_root, thumbnails_root = _resolve_clip_paths(cfg, clips_dir)
    clips_root.mkdir(parents=True, exist_ok=True)
    resolved.temp.mkdir(parents=True, exist_ok=True)

    plans = _plan_clips(filtered, cfg.clip, game_mode=game_mode)
    result = _read_result(session, seg_range, ffmpeg_path, hwaccel, search_from=result_search_from)
    if result is not None and on_result is not None:
        on_result(result)
    result_image_path = _save_result_image(result, thumbnails_root / result_image_name(match_start), clips_root)
    if on_progress is not None:
        on_progress(RESULT_SCAN_PROGRESS_FRACTION)
    portraits = _find_portraits(session, seg_range, ffmpeg_path, hwaccel)
    portrait_paths = _save_portrait_images(portraits, match_start, thumbnails_root, clips_root)

    written: list[Path] = []
    phase_clip_counts: dict[int | None, int] = {}
    for i, plan in enumerate(plans, start=1):
        aggregated = _aggregate_interval(plan.intervals)
        phase_clip_index = next_phase_clip_index(phase_clip_counts, aggregated.cobalt_phase)
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
            thumbnail_rel = stored_asset_path(thumb_path, clips_root)

        meta = build_metadata(
            title=default_title(
                aggregated.day_night, aggregated.region, aggregated.game_day,
                cobalt_phase=aggregated.cobalt_phase, clip_index=phase_clip_index,
            ),
            game_day=aggregated.game_day,
            pvp=score_interval(aggregated, cfg.filter.pvp_weights),
            session=session,
            match_start_utc=match_start,
            game_mode=game_mode,
            interval=aggregated,
            clip_range=plan.range,
            cut_result=cut_result,
            thumbnail_path=thumbnail_rel,
            match_kills=detection.k_final,
            match_assists=detection.a_final,
            match_result=result,
            result_image_path=result_image_path,
            match_end_utc=match_end,
            my_character_portrait_path=portrait_paths["me"],
            teammate_portrait_paths=[
                p for p in (portrait_paths["teammate1"], portrait_paths["teammate2"]) if p
            ],
        )
        meta_path = clip_path.with_suffix(".json")
        write_metadata(meta, meta_path)
        written.append(meta_path)

        if on_progress is not None:
            remaining = 1.0 - RESULT_SCAN_PROGRESS_FRACTION
            on_progress(RESULT_SCAN_PROGRESS_FRACTION + remaining * i / len(plans))

    if written:
        cleanup_preview_registry.notify_clips_changed()
    return written
