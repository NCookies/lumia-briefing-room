"""이미 분석한 옛 영상의 게임을 풀영상으로 만든다. (plan-fullvideo.md §3.7, F6)

게임 위치(영상 색인의 `games[]`)와 판독 캐시가 남아 있으니 영상을 다시 판독하지 않는다. 게임 앞 선택 화면을 찾으려고 게임 시작 앞
150초의 키프레임만 읽고, 결과 화면·초상화를 다시 찾고, 원본에서 풀영상만 자른다. 후보·마커는 캐시된 판독으로 다시 계산한다.
저장해 둔 옛 클립은 지우거나 다시 자르지 않고 같은 후보에 저장됨으로 이어 준다. 이미 풀영상이 있는 게임은 건드리지 않는다.
"""

from __future__ import annotations

import logging
import shutil
import threading
from collections.abc import Callable, Collection
from dataclasses import replace
from pathlib import Path

from lumia_briefing_room.config import Config
from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.detect.types import FrameState, PortraitCrops
from lumia_briefing_room.pipeline.filters import apply_filter
from lumia_briefing_room.pipeline.game_store import FULL_VIDEO, GAME_JSON, is_certain, vod_game_key
from lumia_briefing_room.pipeline.orchestrator import _plan_clips
from lumia_briefing_room.pipeline.vod_analyze import (
    FindPortraits,
    FindResult,
    VodCancelled,
    _default_find_portraits,
    _default_find_result,
    _default_reader,
    _keep_pinned,
    _safe_portraits,
    _safe_result,
)
from lumia_briefing_room.pipeline.vod_detect import detect_games
from lumia_briefing_room.pipeline.vod_full_games import (
    VodSource,
    cut_vod_full_video,
    effective_start,
    name_vod_candidates,
    save_game_assets,
    vod_game_dict,
    vod_game_range,
    write_vod_game,
)
from lumia_briefing_room.pipeline.vod_games import SELECT_MAX_BEFORE_GAME_SEC, GameSpan, selection_before
from lumia_briefing_room.pipeline.vod_store import StateCache, cache_path, save_index
from lumia_briefing_room.video.vod import VodFileSource, find_ffprobe

log = logging.getLogger(__name__)

FindSelection = Callable[[Path, GameSpan, "float | None"], "tuple[float | None, bool]"]


class UpgradeError(Exception):
    """풀영상을 만들 수 없는 이유를 사용자에게 그대로 보여 줄 수 있는 문장으로 담는다."""


def can_upgrade(index: dict | None, video_path: Path, root: Path) -> bool:
    """원본 영상이 있고, 게임 위치가 색인에 있고, 판독 캐시가 남아 있다."""
    if not index or not index.get("games") or not video_path.is_file() or not index.get("decodeDone"):
        return False
    return cache_path(root, index["id"]).is_file()


def _default_find_selection(
    ffmpeg_path: Path, width: int, height: int, hwaccel: str | None, video_path: Path
) -> FindSelection:
    read = _default_reader(width, height)
    ffprobe_path = find_ffprobe(ffmpeg_path)

    def find(video: Path, span: GameSpan, floor: float | None) -> tuple[float | None, bool]:
        lo = max(0.0, span.start - SELECT_MAX_BEFORE_GAME_SEC - 5.0)
        source = VodFileSource(
            video, ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path, start_sec=lo, end_sec=span.start, hwaccel=hwaccel
        )
        frames = source.frames()
        try:
            states = [read(frame, t) for t, frame in frames]
        finally:
            frames.close()
        return selection_before(states, span.start, floor=floor if floor is not None else float("-inf"))

    return find


def _link_old_clips(candidates, clip_ids_by_overlap: dict[str, tuple[float, float]], full_start: float) -> dict[str, str]:
    """후보 ID 와 같은 옛 클립은 그대로, 나머지는 원본 영상 안 시간이 가장 많이 겹치는 후보에 하나씩 잇는다."""
    linked: dict[str, str] = {}
    free = dict(clip_ids_by_overlap)
    for cand in candidates:
        if cand.clip_id in free:
            linked[cand.candidate_id] = cand.clip_id
            free.pop(cand.clip_id)
    for cand in candidates:
        if cand.candidate_id in linked:
            continue
        lo, hi = cand.plan.range.start, cand.plan.range.end
        best = max(((min(hi, e) - max(lo, s), cid) for cid, (s, e) in free.items()), default=(0.0, None))
        if best[1] is not None and best[0] > 0:
            linked[cand.candidate_id] = best[1]
            free.pop(best[1])
    return linked


def _old_clip_spans(root: Path, game: dict) -> dict[str, tuple[float, float]]:
    import json

    spans: dict[str, tuple[float, float]] = {}
    for clip_id in game.get("clipIds") or []:
        try:
            meta = json.loads((root / f"{clip_id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        start = float(meta.get("videoOffsetSec") or 0.0)
        spans[clip_id] = (start, start + float(meta.get("durationSec") or 0.0))
    return spans


def upgrade_vod_games(
    video_path: Path,
    cfg: Config,
    *,
    ffmpeg_path: Path,
    root: Path,
    games_dir: Path,
    index: dict,
    only: Collection[int] | None = None,
    hwaccel: str | None = None,
    find_result: FindResult | None = None,
    find_portraits: FindPortraits | None = None,
    find_selection: FindSelection | None = None,
    cancel: threading.Event | None = None,
    on_progress: Callable[[float, str], None] | None = None,
) -> list[str]:
    """풀영상을 새로 만든 게임 키 목록. `only` 는 게임 번호 목록(없으면 전부). 이미 풀영상이 있는 게임은 건너뛴다."""
    video_path = Path(video_path)
    if not video_path.is_file():
        raise UpgradeError("원본 영상 파일이 없어 풀영상을 만들 수 없습니다")
    if not can_upgrade(index, video_path, root):
        raise UpgradeError("이전 분석 기록(판독 캐시)이 없어 풀영상을 만들 수 없습니다. 다시 분석하세요")
    vod = index["id"]
    states: list[FrameState] = StateCache(cache_path(root, vod)).load()
    if not states:
        raise UpgradeError("이전 분석 기록(판독 캐시)이 비어 있어 풀영상을 만들 수 없습니다. 다시 분석하세요")
    hwaccel = hwaccel or cfg.vod.hwaccel
    width, height, duration = index["width"], index["height"], float(index["durationSec"])
    find_result = find_result or _default_find_result(ffmpeg_path, width, height, hwaccel)
    find_portraits = find_portraits or _default_find_portraits(ffmpeg_path, width, height, hwaccel)
    find_selection = find_selection or _default_find_selection(ffmpeg_path, width, height, hwaccel, video_path)
    source = VodSource(
        vod_id=vod, path=video_path, streamer=index.get("streamer"), width=width, height=height,
        duration_sec=duration, size_bytes=index.get("size") or video_path.stat().st_size,
    )

    entries = [g for g in index["games"] if only is None or g["index"] in only]
    todo = []
    for g in entries:
        folder = games_dir / vod_game_key(vod, g["index"])
        if _is_settled(folder):
            continue
        todo.append(g)

    def report(done: int, message: str = "") -> None:
        if on_progress is not None:
            on_progress(done / max(1, len(todo)), message)

    created: list[str] = []
    ordered = sorted(index["games"], key=lambda g: g["startSec"])
    for n, g in enumerate(todo):
        if cancel is not None and cancel.is_set():
            raise VodCancelled()
        report(n, f"게임 {g['index']} 풀영상")
        pos = ordered.index(g)
        prev_end = ordered[pos - 1]["endSec"] if pos > 0 else None
        nxt = ordered[pos + 1] if pos + 1 < len(ordered) else None
        span = GameSpan(index=g["index"], start=g["startSec"], end=g["endSec"], confidence=g.get("confidence", 1.0))
        select_start, practice = find_selection(video_path, span, prev_end)
        if practice:
            log.info("게임 %d 는 연습 모드라 풀영상을 만들지 않는다", g["index"])
            continue
        span = replace(span, select_start=select_start)
        next_span = GameSpan(index=nxt["index"], start=nxt["startSec"], end=nxt["endSec"], confidence=1.0) if nxt else None
        det = detect_games(states, [span])[0]
        next_start = effective_start(next_span) if next_span else None
        result: ResultScreen | None = _safe_result(find_result, video_path, span, nxt["startSec"] if nxt else None)
        portraits: PortraitCrops | None = _safe_portraits(find_portraits, video_path, span)
        full_start, full_end = vod_game_range(
            span, result_at=result.t if result is not None else None, prev_end=prev_end, next_start=next_start,
            duration=duration,
        )
        key = vod_game_key(vod, g["index"])
        folder = games_dir / key
        full = cut_vod_full_video(
            video_path, full_start, full_end, folder, ffmpeg_path=ffmpeg_path, include_audio=cfg.clip.include_audio,
            source_size=source.size_bytes, source_duration=duration,
        )
        if full.video is None:
            log.warning("게임 %s 풀영상을 만들지 못했다: %s", key, full.error)
            if not (folder / GAME_JSON).exists():
                shutil.rmtree(folder, ignore_errors=True)
            raise UpgradeError(full.error or "풀영상을 만들지 못했습니다")

        candidates = name_vod_candidates(
            _plan_clips(
                apply_filter(det.detection.intervals, cfg.filter, game_mode=det.detection.game_mode), cfg.clip,
                game_mode=det.detection.game_mode,
            ),
            vod, g["index"], duration=duration,
        )
        saved = _link_old_clips(candidates, _old_clip_spans(root, g), full_start)
        result_file, portrait_files = save_game_assets(folder, result, portraits, game_mode=det.detection.game_mode)
        data = vod_game_dict(
            source=source, span=span, game_mode=det.detection.game_mode, detection=det.detection,
            candidates=candidates, saved_ids=saved, full_start=full_start, full_end=full_end, full=full.video,
            error=None, result=result, result_file=result_file, portraits=portrait_files, save_mode=cfg.clip.save_mode,
            cfg=cfg,
        )
        if result is None:
            _keep_old_result(data, folder, root, g)
        old_portraits = _old_portraits(folder) if det.detection.game_mode != "cobalt" else {}
        data["portraits"] = {slot: name or old_portraits.get(slot) for slot, name in data["portraits"].items()}
        write_vod_game(folder, _keep_pinned(folder, data))
        g.update(gameKey=key, fullVideo=True, fullStartSec=full_start, fullEndSec=full_end)
        save_index(root, index)
        created.append(key)
        report(n + 1)
    return created


def _is_settled(folder: Path) -> bool:
    """이미 새 형식이고 풀영상이 있거나(자동 정리로 지운 것도) 다시 만들 필요가 없는 게임."""
    import json

    try:
        data = json.loads((folder / GAME_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict) or data.get("legacy"):
        return False
    return bool(data.get("fullVideo")) and (folder / FULL_VIDEO).is_file() or bool(data.get("fullVideoDeletedAt"))


def _keep_old_result(data: dict, folder: Path, root: Path, game: dict) -> None:
    """결과 화면을 다시 못 찾았으면 예전 분석이 읽은 결과(이미지는 이미 게임 폴더로 복사돼 있다)를 그대로 둔다."""
    import json

    old = None
    try:
        old = json.loads((folder / GAME_JSON).read_text(encoding="utf-8")).get("matchResult")
    except (OSError, ValueError):
        pass
    if old is None and isinstance(game.get("result"), dict):
        old = {k: v for k, v in game["result"].items() if k != "imagePath"}
    data["matchResult"] = old


def _old_portraits(folder: Path) -> dict[str, str | None]:
    """이번에 초상화를 못 찾았어도 게임 폴더에 이미 복사돼 있는 옛 초상화 파일은 그대로 쓴다."""
    return {
        slot: f"portrait_{slot}.jpg" for slot in ("me", "teammate1", "teammate2")
        if (folder / f"portrait_{slot}.jpg").is_file()
    }
