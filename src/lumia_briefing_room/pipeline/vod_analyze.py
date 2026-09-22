from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from lumia_briefing_room.config import Config, resolve_paths
from lumia_briefing_room.detect.match import (
    analyze_frame,
    resolve_day_templates,
    resolve_region_templates,
    resolve_templates,
)
from lumia_briefing_room.detect.pvp import score_interval
from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.pipeline.clip import ClipRange, make_thumbnail
from lumia_briefing_room.pipeline.filters import apply_filter
from lumia_briefing_room.pipeline.label_migrate import load_metas, migrate_labels
from lumia_briefing_room.pipeline.metadata import match_result_dict
from lumia_briefing_room.pipeline.orchestrator import (
    _aggregate_interval,
    _plan_clips,
    _save_result_image,
    default_title,
)
from lumia_briefing_room.pipeline.retention import trash_clip
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

ANALYSIS_VERSION = 2
CHECKPOINT_FRAMES = 120
PROGRESS_EVERY_FRAMES = 30
DECODE_SHARE = 0.70
GAMES_SHARE = 0.10


class VodCancelled(Exception):
    """사용자가 분석을 취소했다. 여기까지의 판독은 캐시에 남아 이어할 수 있다."""


@dataclass(frozen=True)
class VodProgress:
    phase: str
    fraction: float
    games: int = 0
    clips: int = 0
    message: str = ""


ReadFrame = Callable[[np.ndarray, float], FrameState]
FindResult = Callable[[Path, GameSpan, "float | None"], "ResultScreen | None"]
SourceFactory = Callable[[float], FrameSource]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_reader(width: int, height: int) -> ReadFrame:
    profile = ResolutionProfile.for_resolution(width, height)
    k, a = resolve_templates(profile, None, None)
    regions = resolve_region_templates(profile)
    days = resolve_day_templates(profile)

    def read(frame: np.ndarray, t: float) -> FrameState:
        return analyze_frame(
            frame, profile, t=t, k_templates=k, a_templates=a,
            region_templates=regions, day_templates=days,
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


def _trash_existing_clips(root: Path, vod: str) -> list[dict]:
    """기존 클립을 휴지통으로 옮기고, 라벨을 새 클립으로 옮길 수 있게 옛 메타데이터를 돌려준다."""
    paths = sorted(root.glob(f"vod_{vod}_*.json"))
    olds = load_metas(paths)
    for meta_path in paths:
        trash_clip(meta_path, root / ".trash")
    return olds


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
    source_factory: SourceFactory | None = None,
) -> dict:
    """다시보기 영상 하나를 분석해 게임별 교전 클립을 만든다.

    판독(디코딩)은 캐시에 이어 쓰므로 취소·종료 뒤 다시 부르면 저장된 시각부터 이어간다.
    이미 끝난 영상은 아무것도 안 한다. force 는 캐시까지 지우고 처음부터, rebuild 는 캐시로 클립만 다시 만든다.
    다시 만들 때 기존 클립은 휴지통으로 옮긴다. 원본 영상은 읽기만 한다.
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
        "fps": info.fps, "streamer": streamer, "status": "analyzing", "error": None,
        "decodeDone": bool(index.get("decodeDone")) and not force and not stale,
        "analysisVersion": ANALYSIS_VERSION,
        "updatedAt": _now_iso(),
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
            cancel, report,
        )
    except VodCancelled:
        index.update(status="cancelled", updatedAt=_now_iso())
        save_index(root, index)
        raise
    except Exception as exc:
        index.update(status="error", error=str(exc), updatedAt=_now_iso())
        save_index(root, index)
        raise

    index.update(status="done", updatedAt=_now_iso())
    save_index(root, index)
    report("done", 1.0, games=len(index["games"]), clips=len(index["clips"]))
    return index


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
    cancel: threading.Event | None,
    report: Callable[..., None],
) -> None:
    vod = index["id"]
    spans = split_games(
        states, max_gap_sec=cfg.vod.game_gap_sec, min_game_sec=cfg.vod.min_game_sec
    )
    detections = detect_games(states, spans)
    olds = _trash_existing_clips(root, vod)
    thumbs = root / ".thumbs"
    games: list[dict] = []
    clip_ids: list[str] = []
    n = max(1, len(detections))

    for i, det in enumerate(detections):
        if cancel is not None and cancel.is_set():
            raise VodCancelled()
        span = det.span
        base = DECODE_SHARE + GAMES_SHARE
        report("games", DECODE_SHARE + GAMES_SHARE * i / n, f"게임 {span.index} 결과 화면", games=len(games), clips=len(clip_ids))
        next_start = spans[i + 1].start if i + 1 < len(spans) else None
        result = _safe_result(find_result, video_path, span, next_start)
        result_image = _save_result_image(result, thumbs / f"{vod}_g{span.index:02d}_result.jpg")

        filtered = apply_filter(det.detection.intervals, cfg.filter, game_mode="battle_royale")
        game_clip_ids: list[str] = []
        for plan in _plan_clips(filtered, cfg.clip):
            if cancel is not None and cancel.is_set():
                raise VodCancelled()
            rng = ClipRange(
                start=max(0.0, plan.range.start),
                end=min(info.duration_sec, plan.range.end),
                preroll_source=plan.range.preroll_source,
            )
            aggregated = _aggregate_interval(plan.intervals)
            clip_id = vod_clip_id(vod, span.index, rng.start)
            clip_path = root / f"{clip_id}.mp4"
            report("cut", base + (1 - base) * i / n, f"게임 {span.index} 클립 {len(game_clip_ids) + 1}",
                   games=len(games), clips=len(clip_ids))
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
                thumb_rel = str(thumb_path)
            meta = build_vod_metadata(
                title=default_title(
                    aggregated.day_night, aggregated.region, aggregated.game_day,
                    [result.character] if result is not None and result.character else [],
                ),
                vod_id=vod, vod_file=str(video_path), streamer=index.get("streamer"),
                game_index=span.index, game_start=span.start, game_end=span.end,
                width=info.width, height=info.height, interval=aggregated, clip_range=rng,
                duration_sec=cut.duration_sec, thumbnail_path=thumb_rel,
                pvp=score_interval(aggregated, cfg.filter.pvp_weights),
                match_kills=det.detection.k_final, match_assists=det.detection.a_final,
                match_result=result, result_image_path=result_image,
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
            "result": match_result_dict(result, result_image), "clipIds": game_clip_ids,
        })

    report_labels = migrate_labels(olds, [root / f"{cid}.json" for cid in clip_ids])
    index.update(
        games=games, clips=clip_ids,
        labelsMigrated=report_labels["migrated"], labelConflicts=report_labels["conflicts"],
    )
