from __future__ import annotations

import json
import logging
import shutil
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from lumia_briefing_room.config import Config, resolve_paths
from lumia_briefing_room.detect.match import (
    analyze_frame,
    resolve_day_templates,
    resolve_phase_templates,
    resolve_region_templates,
    resolve_templates,
    resolve_tk_templates,
)
from lumia_briefing_room.detect.pvp import score_interval
from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.detect.types import FrameState, PortraitCrops
from lumia_briefing_room.pipeline.clip import ClipRange, make_thumbnail
from lumia_briefing_room.pipeline.clip_assets import stored_asset_path
from lumia_briefing_room.pipeline.ffmpeg_errors import describe_clip_error, is_disk_full_error
from lumia_briefing_room.pipeline.filters import apply_filter
from lumia_briefing_room.pipeline.label_migrate import load_metas, migrate_labels
from lumia_briefing_room.pipeline.metadata import match_result_dict
from lumia_briefing_room.pipeline.orchestrator import (
    _aggregate_interval,
    _plan_clips,
    _save_result_image,
    default_title,
    next_phase_clip_index,
)
from lumia_briefing_room.pipeline.portrait_scan import PORTRAIT_SLOTS, find_vod_portraits, save_portrait_image
from lumia_briefing_room.pipeline.delete_helper import delete_clip, permanently_delete, send_to_recycle_bin
from lumia_briefing_room.pipeline.label_archive import archive_dir_for
from lumia_briefing_room.pipeline.vod_clips import build_vod_metadata, cut_vod_clip, vod_clip_id
from lumia_briefing_room.pipeline.vod_detect import detect_games
from lumia_briefing_room.pipeline.vod_games import GameSpan, split_games
from lumia_briefing_room.pipeline.vod_result import find_vod_result
from lumia_briefing_room.pipeline.vod_store import (
    StateCache,
    cache_path,
    load_index,
    save_index,
    vod_id,
)
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.source import FrameSource
from lumia_briefing_room.video.vod import VodFileSource, find_ffprobe, probe_video

log = logging.getLogger(__name__)

# 3: TK 판독 추가 + 배지 꺼진 뒤 트레일링 킬로 구간 끝 늘리기(2026-09-23) - 캐시된
# FrameState 에는 tk 가 없어 이 로직이 못 살아나므로 캐시를 무효화해야 한다.
# 4: 코발트 프로토콜 지원(2026-09-27, plan.md §10) - `cobalt_phase` 판독 추가.
# 이전 캐시는 phase_templates 를 아예 연결하지 않았을 때 만들어져 `cobalt_phase`
# 가 전부 None 이라 `is_ingame()`/`infer_game_mode` 가 코발트 게임을 하나도 못
# 찾는다(실사용 사고: 코발트 다시보기 1편이 games=0 으로 "분석 완료"돼 버렸다 -
# 목록에서도 사라진다, `keptEmpty` 필터가 "분석 끝났는데 클립 0개"인 영상을 숨기므로).
# 5: 코발트 TK/K/A HUD 위치 보정(2026-09-27, plan.md §10-3 후속) - 코발트는 같은
# 스트리머의 배틀로얄 녹화 대비 TK/K/A 칸이 ~80px 왼쪽에 있다는 걸 실측으로 확인해
# `analyze_frame`이 그 자리도 시도하도록 고쳤다. 이전 캐시는 그 자리를 아예 안 봐서
# k/a/tk 가 전부 None 이라 교전 구간을 하나도 못 만든다(실사용 사고: 코발트 6게임
# 전부 결과 화면은 읽혔는데 클립이 0개).
ANALYSIS_VERSION = 5
CHECKPOINT_FRAMES = 120
PROGRESS_EVERY_FRAMES = 30
# 진행률은 화면의 각 구간이 실제로 걸리는 시간에 비례해야 한다(2026-09-27 사용자 보고 -
# "다시 분석"을 누르면 70%까지 순식간에 뛰었다가 나머지 30%는 한참 밍기적거려 기대하게
# 만들지 말라는 피드백. 원인은 반대였다: 디코드(키프레임만 읽어 ~50배속, plan-vod.md)는
# 제일 빠른 단계인데 막대의 70%를 차지했고, 실제로 시간이 제일 오래 걸리는 클립 컷
# (ffmpeg 재인코딩 + 썸네일)은 나머지 20%에 몰려 있었다. 3시간18분/8게임/106클립 영상
# 실측(plan-vod.md, 총 12분) 기준으로 디코드는 전체의 일부일 뿐이고 컷이 대부분을 먹는다.
DECODE_SHARE = 0.15
GAMES_SHARE = 0.10


class VodCancelled(Exception):
    """사용자가 분석을 취소했다. 여기까지의 판독은 캐시에 남아 이어할 수 있다."""


class VodAnalyzeError(Exception):
    """다시 만들었지만 클립이 하나도 안 나와, 기존 클립을 지우지 않고 실패로 남긴 경우."""


@dataclass(frozen=True)
class VodProgress:
    phase: str
    fraction: float
    games: int = 0
    clips: int = 0
    message: str = ""


ReadFrame = Callable[[np.ndarray, float], FrameState]
FindResult = Callable[[Path, GameSpan, "float | None"], "ResultScreen | None"]
FindPortraits = Callable[[Path, GameSpan], "PortraitCrops | None"]
SourceFactory = Callable[[float], FrameSource]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_reader(width: int, height: int) -> ReadFrame:
    profile = ResolutionProfile.for_resolution(width, height)
    k, a = resolve_templates(profile, None, None)
    tk = resolve_tk_templates(profile, k)
    regions = resolve_region_templates(profile)
    days = resolve_day_templates(profile)
    phases = resolve_phase_templates(profile)

    def read(frame: np.ndarray, t: float) -> FrameState:
        return analyze_frame(
            frame, profile, t=t, k_templates=k, a_templates=a, tk_templates=tk,
            region_templates=regions, day_templates=days, phase_templates=phases,
        )

    return read


def _default_find_result(ffmpeg_path: Path, width: int, height: int, hwaccel: str | None) -> FindResult:
    profile = ResolutionProfile.for_resolution(width, height)

    def find(video: Path, span: GameSpan, next_start: float | None) -> ResultScreen | None:
        return find_vod_result(
            video, span, next_start, ffmpeg_path=ffmpeg_path, profile=profile, hwaccel=hwaccel
        )

    return find


def _safe_result(find: FindResult, video: Path, span: GameSpan, next_start: float | None) -> ResultScreen | None:
    """결과 화면 판독은 부가 정보라 실패해도 클립 생성을 막지 않는다."""
    try:
        return find(video, span, next_start)
    except Exception:
        log.exception("게임 %d 결과 화면 판독 실패 - 순위 없이 저장한다", span.index)
        return None


def _default_find_portraits(ffmpeg_path: Path, width: int, height: int, hwaccel: str | None) -> FindPortraits:
    profile = ResolutionProfile.for_resolution(width, height)

    def find(video: Path, span: GameSpan) -> PortraitCrops | None:
        return find_vod_portraits(video, span, ffmpeg_path=ffmpeg_path, profile=profile, hwaccel=hwaccel)

    return find


def _safe_portraits(find: FindPortraits, video: Path, span: GameSpan) -> PortraitCrops | None:
    """초상화 판독도 부가 정보라 실패해도 클립 생성을 막지 않는다."""
    try:
        return find(video, span)
    except Exception:
        log.exception("게임 %d 초상화 판독 실패 - 초상화 없이 저장한다", span.index)
        return None


def _vod_portrait_image_name(vod: str, game_index: int, slot: str) -> str:
    return f"{vod}_g{game_index:02d}_portrait_{slot}.jpg"


def _save_vod_portrait_images(
    portraits: PortraitCrops | None, vod: str, game_index: int, thumbs: Path, root: Path
) -> dict[str, str | None]:
    paths: dict[str, str | None] = {slot: None for slot in PORTRAIT_SLOTS}
    if portraits is None:
        return paths
    for slot in PORTRAIT_SLOTS:
        path = thumbs / _vod_portrait_image_name(vod, game_index, slot)
        try:
            save_portrait_image(getattr(portraits, slot), path)
        except OSError:
            log.exception("초상화 이미지 저장 실패(%s)", slot)
            continue
        paths[slot] = stored_asset_path(path, root)
    return paths


STAGING_DIRNAME = ".staging"


def _existing_clip_paths(root: Path, vod: str) -> list[Path]:
    return sorted(root.glob(f"vod_{vod}_*.json"))


def _move_staged_tree(staging: Path, dest_root: Path) -> None:
    for path in sorted(staging.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(staging)
        dest = dest_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest))
    shutil.rmtree(staging, ignore_errors=True)


def analyze_vod(
    video_path: Path,
    cfg: Config,
    *,
    ffmpeg_path: Path,
    clips_dir: Path | None = None,
    streamer: str | None = None,
    hwaccel: str | None = None,
    force: bool = False,
    rebuild: bool = False,
    on_progress: Callable[[VodProgress], None] | None = None,
    cancel: threading.Event | None = None,
    read_frame: ReadFrame | None = None,
    find_result: FindResult | None = None,
    find_portraits: FindPortraits | None = None,
    source_factory: SourceFactory | None = None,
    delete_source: bool | None = None,
) -> dict:
    """다시보기 영상 하나를 분석해 게임별 교전 클립을 만든다.

    판독(디코딩)은 캐시에 이어 쓰므로 취소·종료 뒤 다시 부르면 저장된 시각부터 이어간다.
    이미 끝난 영상은 아무것도 안 한다. force 는 캐시까지 지우고 처음부터, rebuild 는 캐시로 클립만 다시 만든다.
    다시 만들 때 새 클립을 전부 만든 뒤에만 기존 클립을 지운다(설정한 삭제 방식). 원본 영상은 기본적으로 읽기만 한다.

    `delete_source` 는 분석이 성공하고 클립이 1개 이상 나왔을 때 원본 영상 파일을 지울지
    정한다(plan-vod.md V7). `None` 이면 이전 호출에서 저장해 둔 값(`index["deleteSourceOnSuccess"]`,
    기본 False)을 그대로 따른다 — 취소된 분석을 다시 부르는 등 이번 호출에서 값을 다시 넘기지
    않아도 처음에 고른 선택이 이어진다.
    """
    video_path = Path(video_path)
    root = clips_dir or resolve_paths(cfg.paths).vod_clips
    root.mkdir(parents=True, exist_ok=True)
    ffprobe_path = find_ffprobe(ffmpeg_path)
    info = probe_video(video_path, ffprobe_path=ffprobe_path)
    vod = vod_id(video_path)
    hwaccel = hwaccel or cfg.vod.hwaccel
    streamer = streamer or cfg.vod.streamers.get(vod)
    cache = StateCache(cache_path(root, vod))

    def report(phase: str, fraction: float, message: str = "", *, games: int = 0, clips: int = 0) -> None:
        if on_progress is not None:
            on_progress(VodProgress(phase, min(1.0, fraction), games, clips, message))

    index = load_index(root, vod) or {}
    if index.get("status") == "done" and not force and not rebuild:
        return index
    stale = bool(index) and index.get("analysisVersion", 1) != ANALYSIS_VERSION
    if force:
        cache.clear()
        index = {}
    elif stale:
        cache.clear()
        index = {**index, "decodeDone": False, "analyzedSec": 0.0}
    index = {
        **index,
        "id": vod, "path": str(video_path), "size": video_path.stat().st_size,
        "durationSec": info.duration_sec, "width": info.width, "height": info.height,
        "fps": info.fps, "creationTime": info.creation_time, "streamer": streamer, "status": "analyzing",
        "error": None, "errorKind": None,
        "decodeDone": bool(index.get("decodeDone")) and not force and not stale,
        "analysisVersion": ANALYSIS_VERSION,
        "updatedAt": _now_iso(),
        "deleteSourceOnSuccess": delete_source if delete_source is not None else index.get("deleteSourceOnSuccess", False),
    }
    save_index(root, index)

    def factory(start: float) -> FrameSource:
        if source_factory is not None:
            return source_factory(start)
        return VodFileSource(
            video_path, ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path,
            start_sec=start, hwaccel=hwaccel,
        )

    try:
        states = _decode(
            cache, index, factory, read_frame or _default_reader(info.width, info.height),
            info.duration_sec, cancel, root, report,
        )
        _make_clips(
            video_path, cfg, ffmpeg_path, root, index, states, info,
            find_result or _default_find_result(ffmpeg_path, info.width, info.height, hwaccel),
            find_portraits or _default_find_portraits(ffmpeg_path, info.width, info.height, hwaccel),
            cancel, report,
        )
    except VodCancelled:
        index.update(status="cancelled", updatedAt=_now_iso())
        save_index(root, index)
        raise
    except Exception as exc:
        index.update(
            status="error",
            error=describe_clip_error(exc),
            errorKind="disk_full" if is_disk_full_error(exc) else "other",
            updatedAt=_now_iso(),
        )
        save_index(root, index)
        raise

    index.update(status="done", updatedAt=_now_iso())
    save_index(root, index)
    if index.get("deleteSourceOnSuccess") and len(index["clips"]) >= 1:
        _delete_source_video(video_path, mode=cfg.vod.delete_source_mode)
    report("done", 1.0, games=len(index["games"]), clips=len(index["clips"]))
    return index


def _delete_source_video(path: Path, *, mode: str) -> None:
    """분석이 끝난 뒤 사용자가 선택한 경우에만 원본 영상 파일 하나를 지운다. (plan-vod.md V7)

    폴더나 다른 파일은 건드리지 않고, 방금 분석한 이 경로 하나만 지운다.
    """
    if not path.exists():
        return
    if mode == "permanent":
        permanently_delete([path])
    else:
        send_to_recycle_bin([path])


def _decode(
    cache: StateCache,
    index: dict,
    factory: SourceFactory,
    read_frame: ReadFrame,
    duration: float,
    cancel: threading.Event | None,
    root: Path,
    report: Callable[..., None],
) -> list[FrameState]:
    states = cache.load()
    if index.get("decodeDone"):
        return states

    start = states[-1].t + 0.5 if states else 0.0
    pending: list[FrameState] = []
    gen = factory(start).frames()

    def flush() -> None:
        nonlocal pending
        cache.append(pending)
        states.extend(pending)
        pending = []
        index.update(analyzedSec=states[-1].t if states else 0.0, updatedAt=_now_iso())
        save_index(root, index)

    try:
        for count, (t, frame) in enumerate(gen, start=1):
            if cancel is not None and cancel.is_set():
                flush()
                raise VodCancelled()
            pending.append(read_frame(frame, t))
            if len(pending) >= CHECKPOINT_FRAMES:
                flush()
            if count % PROGRESS_EVERY_FRAMES == 0:
                report("decode", DECODE_SHARE * (t / duration) if duration else 0.0, f"{t:.0f}초 / {duration:.0f}초")
    finally:
        gen.close()
    if cancel is not None and cancel.is_set():
        flush()
        raise VodCancelled()
    flush()
    index.update(decodeDone=True)
    save_index(root, index)
    report("decode", DECODE_SHARE)
    return states


def _make_clips(
    video_path: Path,
    cfg: Config,
    ffmpeg_path: Path,
    root: Path,
    index: dict,
    states: list[FrameState],
    info,
    find_result: FindResult,
    find_portraits: FindPortraits,
    cancel: threading.Event | None,
    report: Callable[..., None],
) -> None:
    """새 클립은 스테이징 폴더에 만들고, 다 만든 뒤에만 기존 클립을 지우고 실제 위치로 옮긴다.

    취소되거나 실패하면 스테이징만 지우고 기존 클립은 그대로 둔다(docs/plan-ui.md §0-(6))."""
    vod = index["id"]
    spans = split_games(
        states, max_gap_sec=cfg.vod.game_gap_sec, min_game_sec=cfg.vod.min_game_sec
    )
    detections = detect_games(states, spans)
    old_paths = _existing_clip_paths(root, vod)
    olds = load_metas(old_paths)
    staging = root / STAGING_DIRNAME / uuid.uuid4().hex
    thumbs = staging / ".thumbs"
    games: list[dict] = []
    clip_ids: list[str] = []
    n = max(1, len(detections))

    # 컷 단계 진행률을 게임 수가 아니라 클립 수에 비례하게 하려고 미리 계획을 전부
    # 세운다(plan-backfill.md B8 - 클립이 몰린 게임 하나 처리하는 동안 막대가 멈춘 듯
    # 보이던 문제, 2026-09-27). apply_filter/_plan_clips 는 이미 계산된 interval 을
    # 훑을 뿐 I/O 가 없어 두 번 부르는 대신 여기서 한 번만 계산해 재사용한다.
    plans_by_game = [
        _plan_clips(
            apply_filter(det.detection.intervals, cfg.filter, game_mode=det.detection.game_mode), cfg.clip,
            game_mode=det.detection.game_mode,
        )
        for det in detections
    ]
    total_clips = max(1, sum(len(p) for p in plans_by_game))
    base = DECODE_SHARE + GAMES_SHARE
    clips_done = 0

    try:
        for i, det in enumerate(detections):
            if cancel is not None and cancel.is_set():
                raise VodCancelled()
            span = det.span
            report("games", DECODE_SHARE + GAMES_SHARE * i / n, f"게임 {span.index} 결과 화면", games=len(games), clips=len(clip_ids))
            next_start = spans[i + 1].start if i + 1 < len(spans) else None
            result = _safe_result(find_result, video_path, span, next_start)
            result_image = _save_result_image(result, thumbs / f"{vod}_g{span.index:02d}_result.jpg", staging)
            portraits = _safe_portraits(find_portraits, video_path, span)
            portrait_paths = _save_vod_portrait_images(portraits, vod, span.index, thumbs, staging)

            game_clip_ids: list[str] = []
            phase_clip_counts: dict[int | None, int] = {}
            for plan in plans_by_game[i]:
                if cancel is not None and cancel.is_set():
                    raise VodCancelled()
                rng = ClipRange(
                    start=max(0.0, plan.range.start),
                    end=min(info.duration_sec, plan.range.end),
                    preroll_source=plan.range.preroll_source,
                )
                aggregated = _aggregate_interval(plan.intervals)
                phase_clip_index = next_phase_clip_index(phase_clip_counts, aggregated.cobalt_phase)
                clip_id = vod_clip_id(vod, span.index, rng.start)
                clip_path = staging / f"{clip_id}.mp4"
                report("cut", base + (1 - base) * clips_done / total_clips, f"게임 {span.index} 클립 {len(game_clip_ids) + 1}",
                       games=len(games), clips=len(clip_ids))
                clips_done += 1
                cut = cut_vod_clip(
                    video_path, rng, clip_path, ffmpeg_path=ffmpeg_path, include_audio=cfg.clip.include_audio
                )
                thumb_rel = None
                if cfg.encode.thumbnail.enabled:
                    thumb_path = thumbs / f"{clip_id}.jpg"
                    make_thumbnail(
                        clip_path, thumb_path, duration_sec=cut.duration_sec,
                        offset_ratio=cfg.encode.thumbnail.offset_ratio,
                        width=cfg.encode.thumbnail.width, ffmpeg_path=ffmpeg_path,
                    )
                    thumb_rel = stored_asset_path(thumb_path, staging)
                meta = build_vod_metadata(
                    title=default_title(
                        aggregated.day_night, aggregated.region, aggregated.game_day,
                        cobalt_phase=aggregated.cobalt_phase, clip_index=phase_clip_index,
                    ),
                    vod_id=vod, vod_file=str(video_path), streamer=index.get("streamer"),
                    game_mode=det.detection.game_mode,
                    game_index=span.index, game_start=span.start, game_end=span.end,
                    width=info.width, height=info.height, interval=aggregated, clip_range=rng,
                    duration_sec=cut.duration_sec, thumbnail_path=thumb_rel,
                    pvp=score_interval(aggregated, cfg.filter.pvp_weights),
                    match_kills=det.detection.k_final, match_assists=det.detection.a_final,
                    match_result=result, result_image_path=result_image,
                    my_character_portrait_path=portrait_paths["me"],
                    teammate_portrait_paths=[
                        p for p in (portrait_paths["teammate1"], portrait_paths["teammate2"]) if p
                    ],
                )
                clip_path.with_suffix(".json").write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                game_clip_ids.append(clip_id)
                clip_ids.append(clip_id)

            games.append({
                "index": span.index, "startSec": span.start, "endSec": span.end,
                "confidence": span.confidence,
                "kFinal": det.detection.k_final, "aFinal": det.detection.a_final,
                "gameMode": det.detection.game_mode,
                "result": match_result_dict(result, result_image), "clipIds": game_clip_ids,
            })
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    if not clip_ids and old_paths:
        shutil.rmtree(staging, ignore_errors=True)
        raise VodAnalyzeError("다시 만들었지만 이 영상에서 클립을 찾지 못했습니다. 기존 클립을 그대로 둡니다")

    report_labels = migrate_labels(olds, [staging / f"{cid}.json" for cid in clip_ids])

    archive_dir = archive_dir_for(root)
    for meta_path in old_paths:
        delete_clip(meta_path, mode=cfg.ui.delete_mode, archive_dir=archive_dir)
    _move_staged_tree(staging, root)

    index.update(
        games=games, clips=clip_ids,
        labelsMigrated=report_labels["migrated"], labelConflicts=report_labels["conflicts"],
    )
