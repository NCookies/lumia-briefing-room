import logging
import shutil
import threading
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from lumia_briefing_room.config import ClipConfig, Config, resolve_paths
from lumia_briefing_room.detect.match import detect_match
from lumia_briefing_room.detect.pvp import score_interval
from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.detect.types import CombatInterval, MatchDetection
from lumia_briefing_room.pipeline.clip_uid import new_clip_uid
from lumia_briefing_room.pipeline.clip import ClipRange, copy_rate_for, cut_clip, make_thumbnail, resolve_clip_range
from lumia_briefing_room.detect.types import PortraitCrops
from lumia_briefing_room.pipeline.filters import apply_filter
from lumia_briefing_room.pipeline.full_video import FullVideoOutcome, cut_full_video
from lumia_briefing_room.pipeline.recording_stop import STOPPED_DURING_MESSAGE
from lumia_briefing_room.pipeline.game_store import (
    SCHEMA_VERSION,
    candidate_dict,
    game_key,
    is_certain,
    markers_dict,
    plans_to_save,
    write_game_json,
)
from lumia_briefing_room.pipeline.metadata import build_metadata, match_result_dict, write_metadata
from lumia_briefing_room.pipeline.clip_assets import stored_asset_path
from lumia_briefing_room.pipeline.cleanup_registry import registry as cleanup_preview_registry
from lumia_briefing_room.pipeline.portrait_scan import (
    PORTRAIT_SLOTS,
    find_match_portraits,
    portrait_image_name,
    save_portrait_image,
)
from lumia_briefing_room.pipeline.result_scan import (
    RESULT_TAIL_SEGMENTS,
    find_result_after,
    find_result_screen,
    result_image_name,
    save_result_image,
)
from lumia_briefing_room.pipeline.result_tail import find_result_in_segments, find_result_in_video
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


def _resolve_clip_paths(cfg: Config, clips_dir: Path | None, video_dir: Path | None = None) -> tuple[Path, Path, Path]:
    """(정보 폴더, 영상 폴더, 썸네일 폴더). 썸네일은 정보 폴더의 `.thumbs` 다.

    `clips_dir` 를 주면(작업 폴더) 정보와 영상이 모두 거기에 만들어진다. 안 주면 정보는 앱 데이터 library, 영상은 저장 폴더.
    """
    if clips_dir is not None:
        meta_root, video_root = clips_dir, video_dir or clips_dir
    else:
        resolved = resolve_paths(cfg.paths)
        meta_root, video_root = resolved.library_steam, video_dir or resolved.clips_steam
    return meta_root, video_root, meta_root / ".thumbs"


def _read_result_tail(
    session, seg_range, ffmpeg_path: Path, hwaccel: str | None, *,
    search_from: datetime | None, full_video: Path | None, tmp_dir: Path | None,
) -> ResultScreen | None:
    """게임 끝부분을 2fps 로 읽는다(풀영상이 있으면 그 끝, 없으면 끝 세그먼트). 실패해도 키프레임 훑기로 넘어간다."""
    try:
        if full_video is not None:
            return find_result_in_video(full_video, ffmpeg_path=ffmpeg_path, hwaccel=hwaccel)
        if tmp_dir is not None:
            last = seg_range.last if search_from is not None else seg_range.last + RESULT_TAIL_SEGMENTS
            return find_result_in_segments(session, last, ffmpeg_path=ffmpeg_path, tmp_dir=tmp_dir, hwaccel=hwaccel)
    except Exception:
        log.exception("게임 끝부분 2fps 판독 실패 - 키프레임 훑기로 넘어간다")
    return None


def _read_result(
    session, seg_range, ffmpeg_path: Path, hwaccel: str | None, *, search_from: datetime | None = None,
    full_video: Path | None = None, tmp_dir: Path | None = None,
) -> ResultScreen | None:
    """결과 화면 판독은 부가 정보라 실패해도 클립 생성을 막지 않는다.

    먼저 게임 끝부분을 초당 2장으로 읽는다(결과 화면이 2~3초만 떠도 잡힌다). 못 찾으면 키프레임(3초 격자) 훑기로 넘어간다.
    로그 기반 경기는 끝이 로비 복귀 시각이라 구간 끝에서 거슬러 오른다. 화면으로 찾은 경기(과거 녹화 복구)는 끝을 '마지막 인게임
    프레임'으로 알 뿐이라 `search_from`(그 시각) 뒤에서 앞으로 훑는다 — 구간 끝(다음 경기 시작 전)까지만 본다.
    """
    tail = _read_result_tail(
        session, seg_range, ffmpeg_path, hwaccel, search_from=search_from, full_video=full_video, tmp_dir=tmp_dir
    )
    if tail is not None:
        return tail
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


@dataclass(frozen=True)
class NamedCandidate:
    candidate_id: str
    clip_id: str
    title: str
    plan: ClipPlan
    aggregated: CombatInterval


def _name_candidates(plans: list[ClipPlan], match_start: datetime) -> list[NamedCandidate]:
    named: list[NamedCandidate] = []
    phase_clip_counts: dict[int | None, int] = {}
    for i, plan in enumerate(plans, start=1):
        aggregated = _aggregate_interval(plan.intervals)
        phase_clip_index = next_phase_clip_index(phase_clip_counts, aggregated.cobalt_phase)
        clip_id = f"{match_start:%Y%m%d_%H%M%S}_{i:02d}"
        title = default_title(
            aggregated.day_night, aggregated.region, aggregated.game_day,
            cobalt_phase=aggregated.cobalt_phase, clip_index=phase_clip_index,
        )
        named.append(NamedCandidate(clip_id, clip_id, title, plan, aggregated))
    return named


def _copy_game_asset(src: Path, dest: Path) -> str | None:
    try:
        shutil.copy2(src, dest)
    except OSError:
        return None
    return dest.name


def _iso_z(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _write_game_record(
    folder: Path,
    *,
    session: RecordingSession,
    match_start: datetime,
    match_end: datetime,
    game_mode: str,
    detection: MatchDetection,
    candidates: list[NamedCandidate],
    saved_ids: dict[str, str],
    full: FullVideoOutcome,
    result: ResultScreen | None,
    thumbnails_root: Path,
    portrait_names: dict[str, str],
    result_name: str,
    cfg: Config,
) -> None:
    """game.json 을 쓴다. 실패해도 클립 결과를 막지 않는다."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        offset = full.video.offset_sec if full.video else 0.0
        result_file = _copy_game_asset(thumbnails_root / result_name, folder / "result.jpg") if result else None
        portraits = {
            slot: _copy_game_asset(thumbnails_root / name, folder / f"portrait_{slot}.jpg")
            for slot, name in portrait_names.items()
        }
        video = None
        if full.video is not None:
            video = {
                "path": full.video.path.name,
                "sizeBytes": full.video.size_bytes,
                "durationSec": full.video.cut.duration_sec,
                "offsetSec": full.video.offset_sec,
                "segmentDurationSec": session.segment_duration_sec,
                "segmentStart": full.video.cut.segment_start,
                "segmentEnd": full.video.cut.segment_end,
                "sourceIncomplete": full.video.cut.source_incomplete,
                "audioStatus": full.video.cut.audio_status,
            }
        candidate_rows = []
        for c in candidates:
            pvp = score_interval(c.aggregated, cfg.filter.pvp_weights)
            candidate_rows.append(candidate_dict(
                c.candidate_id, interval=c.aggregated, start=c.plan.range.start, end=c.plan.range.end,
                preroll_source=c.plan.range.preroll_source, title=c.title, offset_sec=offset,
                pvp_score=pvp.score, pvp_signals=list(pvp.signals), clip_id=saved_ids.get(c.candidate_id),
            ))
        data = {
            "schemaVersion": SCHEMA_VERSION,
            "gameKey": game_key(match_start),
            "source": "steam",
            "sessionDir": session.directory.name,
            "sessionStartUtc": _iso_z(session.start_utc),
            "matchStartUtc": _iso_z(match_start),
            "matchEndUtc": _iso_z(match_end),
            "gameMode": game_mode,
            "sourceWidth": session.width,
            "sourceHeight": session.height,
            "sourceIncomplete": detection.source_incomplete,
            "matchKills": detection.k_final,
            "matchAssists": detection.a_final,
            "matchResult": match_result_dict(result, result_file),
            "portraits": portraits,
            "saveMode": cfg.clip.save_mode,
            "fullVideo": video,
            "fullVideoError": full.error,
            "recordingStopped": full.recording_stopped,
            "candidates": candidate_rows,
            "userCandidates": [],
            "markers": markers_dict(detection.markers, offset_sec=offset),
        }
        write_game_json(folder, data)
    except Exception:
        log.exception("게임 기록(game.json) 저장 실패 - 클립 저장은 계속한다")


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
    video_dir: Path | None = None,
    hwaccel: str | None = None,
    on_result: Callable[[ResultScreen], None] | None = None,
    cancel: threading.Event | None = None,
    result_search_from: datetime | None = None,
    on_progress: Callable[[float], None] | None = None,
    games_dir: Path | None = None,
    on_full_video_error: Callable[[str], None] | None = None,
    on_recording_stopped: Callable[[str], None] | None = None,
    existing_clip_ids: Collection[str] | None = None,
) -> list[Path]:
    """SPEC §3 다이어그램 전체: 매치 하나를 검출부터 메타데이터 저장까지 처리한다.

    `game_mode` 를 안 주면(기본) 검출 결과(`Phase N` vs `N일 차` 판독 횟수, plan.md §10
    C1-b)로 자동 판별한다. 명시하면(CLI `--game-mode` 등) 그 값을 그대로 쓴다.

    검출 직후 게임 전체 영상을 `games/<경기키>/full.mp4` 로 먼저 자르고(실패해도 계속), 클립은
    `clip.saveMode` 가 `auto` 일 때만 자른다(풀영상이 없으면 확실한 후보만). 후보·마커는 `game.json` 에 남긴다.

    `existing_clip_ids` 를 주면(빈 집합도) 이전 버전에서 분석한 게임의 풀영상을 새로 만드는 것이다: 그 ID 의 후보는 저장됨으로
    표시만 하고, 클립은 `saveMode` 와 무관하게 새로 자르지 않는다(사용자가 이미 고른 클립을 두 번 만들지 않는다).

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

    resolved = resolve_paths(cfg.paths)
    clips_root, video_root, thumbnails_root = _resolve_clip_paths(cfg, clips_dir, video_dir)
    game_folder = (games_dir or resolved.games_steam) / game_key(match_start)
    clips_root.mkdir(parents=True, exist_ok=True)
    video_root.mkdir(parents=True, exist_ok=True)
    resolved.temp.mkdir(parents=True, exist_ok=True)

    copy_rate = copy_rate_for(session)
    if copy_rate is not None:
        log.info("스팀이 녹화 중이라 녹화 폴더 복사 속도를 초당 %dMB 로 제한한다", copy_rate // 2**20)

    # 링버퍼가 원본을 지우기 전에 끝나야 하므로 풀영상 컷이 클립 컷보다 먼저다. 실패해도 나머지는 계속한다.
    full = cut_full_video(
        session, seg_range, match_start, match_end, game_folder,
        ffmpeg_path=ffmpeg_path, include_audio=cfg.clip.include_audio, tmp_dir=resolved.temp,
        max_bytes_per_sec=copy_rate,
    )
    if full.recording_stopped is not None:
        if on_recording_stopped is not None:
            on_recording_stopped(full.error or STOPPED_DURING_MESSAGE)
    elif full.error is not None and on_full_video_error is not None:
        on_full_video_error(full.error)

    if on_progress is not None:
        on_progress(DETECTION_PROGRESS_FRACTION)

    plans = _plan_clips(filtered, cfg.clip, game_mode=game_mode)
    result = _read_result(
        session, seg_range, ffmpeg_path, hwaccel, search_from=result_search_from,
        full_video=full.video.path if full.video is not None else None, tmp_dir=resolved.temp,
    )
    if result is not None and on_result is not None:
        on_result(result)
    result_image_path = _save_result_image(result, thumbnails_root / result_image_name(match_start), clips_root)
    if on_progress is not None:
        on_progress(RESULT_SCAN_PROGRESS_FRACTION)
    portraits = _find_portraits(session, seg_range, ffmpeg_path, hwaccel)
    portrait_paths = _save_portrait_images(portraits, match_start, thumbnails_root, clips_root)

    candidates = _name_candidates(plans, match_start)
    to_save = plans_to_save(
        candidates, "manual" if existing_clip_ids is not None else cfg.clip.save_mode, full.video is not None,
        is_certain=lambda c: is_certain(c.aggregated.tags),
    )

    already = existing_clip_ids or ()
    saved_ids: dict[str, str] = {c.candidate_id: c.clip_id for c in candidates if c.clip_id in already}
    to_save = [c for c in to_save if c.clip_id not in already]
    written: list[Path] = []
    try:
        for n, cand in enumerate(to_save, start=1):
            clip_path = video_root / f"{cand.clip_id}.mp4"
            clip_uid = new_clip_uid()
            cut_result = cut_clip(
                session, cand.plan.range, clip_path,
                ffmpeg_path=ffmpeg_path, include_audio=cfg.clip.include_audio,
                tmp_dir=resolved.temp, clip_uid=clip_uid, max_bytes_per_sec=copy_rate,
            )

            thumbnail_rel: str | None = None
            if cfg.encode.thumbnail.enabled:
                thumb_path = thumbnails_root / f"{cand.clip_id}.jpg"
                make_thumbnail(
                    clip_path, thumb_path,
                    duration_sec=cut_result.duration_sec,
                    offset_ratio=cfg.encode.thumbnail.offset_ratio,
                    width=cfg.encode.thumbnail.width,
                    ffmpeg_path=ffmpeg_path,
                )
                thumbnail_rel = stored_asset_path(thumb_path, clips_root)

            aggregated = cand.aggregated
            meta = build_metadata(
                title=cand.title,
                game_day=aggregated.game_day,
                pvp=score_interval(aggregated, cfg.filter.pvp_weights),
                session=session,
                match_start_utc=match_start,
                game_mode=game_mode,
                interval=aggregated,
                clip_range=cand.plan.range,
                cut_result=cut_result,
                thumbnail_path=thumbnail_rel,
                match_kills=detection.k_final,
                match_assists=detection.a_final,
                match_result=result,
                result_image_path=result_image_path,
                match_end_utc=match_end,
                clip_uid=clip_uid,
                my_character_portrait_path=portrait_paths["me"],
                teammate_portrait_paths=[
                    p for p in (portrait_paths["teammate1"], portrait_paths["teammate2"]) if p
                ],
            )
            meta_path = clips_root / f"{cand.clip_id}.json"
            write_metadata(meta, meta_path)
            written.append(meta_path)
            saved_ids[cand.candidate_id] = cand.clip_id

            if on_progress is not None:
                remaining = 1.0 - RESULT_SCAN_PROGRESS_FRACTION
                on_progress(RESULT_SCAN_PROGRESS_FRACTION + remaining * n / len(to_save))
    finally:
        _write_game_record(
            game_folder, session=session, match_start=match_start, match_end=match_end, game_mode=game_mode,
            detection=detection, candidates=candidates, saved_ids=saved_ids, full=full, result=result,
            thumbnails_root=thumbnails_root,
            portrait_names={slot: portrait_image_name(match_start, slot) for slot in PORTRAIT_SLOTS},
            result_name=result_image_name(match_start), cfg=cfg,
        )

    if on_progress is not None:
        on_progress(1.0)
    cleanup_preview_registry.notify_clips_changed()
    return written
