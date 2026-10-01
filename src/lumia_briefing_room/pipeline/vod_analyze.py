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
from lumia_briefing_room.pipeline.clip_files import commit_staged_clips, find_video_for
from lumia_briefing_room.pipeline.clip_uid import new_clip_uid
from lumia_briefing_room.pipeline.ffmpeg_errors import describe_clip_error, is_disk_full_error
from lumia_briefing_room.pipeline.filters import apply_filter
from lumia_briefing_room.pipeline.game_store import GAME_JSON, is_certain, plans_to_save, vod_game_key
from lumia_briefing_room.pipeline.label_migrate import load_metas, migrate_labels
from lumia_briefing_room.pipeline.metadata import match_result_dict
from lumia_briefing_room.pipeline.orchestrator import (
    _plan_clips,
    _save_result_image,
)
from lumia_briefing_room.pipeline.portrait_scan import PORTRAIT_SLOTS, find_vod_portraits, save_portrait_image
from lumia_briefing_room.pipeline.delete_helper import delete_clip, permanently_delete, send_to_recycle_bin
from lumia_briefing_room.pipeline.label_archive import archive_dir_for
from lumia_briefing_room.pipeline.vod_clips import build_vod_metadata, cut_vod_clip
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
# 6: 캐릭터 선택 화면 판독(`select_screen`·`select_practice`, 1080p 프로필 포함) - 이전 캐시에는 이 값이 없어
# 게임 시작을 선택 화면까지 넓히지도, 연습 모드·닷지를 거르지도 못한다(F6 풀영상 범위가 선택 화면부터라서 필요).
# 7: 1080p 는 머리띠가 가려져도 팀원 카드 막대로 선택 화면을 읽는다(2026-10-01) - 이전 캐시의 `select_screen` 은
# 방송 화면에서 13판 중 8판을 놓쳐 풀영상이 선택 화면 없이 게임 10초 앞부터 잘렸다.
ANALYSIS_VERSION = 7
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


@dataclass(frozen=True)
class ClipPlacement:
    """영상 클립이 놓이는 곳. 정보(json·썸네일·색인)는 `root`(library), 영상은 `video_dir`, 작업 폴더는 `staging_base`."""

    video_dir: Path
    video_roots: tuple[Path, ...]
    staging_base: Path


def analyze_vod(
    video_path: Path,
    cfg: Config,
    *,
    ffmpeg_path: Path,
    clips_dir: Path | None = None,
    video_dir: Path | None = None,
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
    games_dir: Path | None = None,
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
    resolved = resolve_paths(cfg.paths)
    root = clips_dir or resolved.library_vod
    games_root = games_dir or resolved.games_vod
    place = ClipPlacement(
        video_dir=video_dir or (root if clips_dir is not None else resolved.clips_vod),
        video_roots=resolved.clip_roots,
        staging_base=root / STAGING_DIRNAME if clips_dir is not None else resolved.staging_vod_clips,
    )
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
            video_path, cfg, ffmpeg_path, root, games_root, index, states, info,
            find_result or _default_find_result(ffmpeg_path, info.width, info.height, hwaccel),
            find_portraits or _default_find_portraits(ffmpeg_path, info.width, info.height, hwaccel),
            cancel, report, place,
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
    if should_delete_source(index):
        _delete_source_video(video_path, mode=cfg.vod.delete_source_mode)
        # 화면이 "영상 파일을 찾을 수 없습니다"(vod.exists=False, VodSection.tsx)를 오류처럼
        # 보여주지 않고 "설정대로 자동 삭제했다"고 구분해서 보여주게 하는 표시
        # (실사용 보고, 2026-09-29 - 원본 삭제를 직접 선택해 놓고 나중에 그 사실을 잊어
        # 버그로 오해했다).
        index.update(sourceDeleted=True, updatedAt=_now_iso())
        save_index(root, index)
    report("done", 1.0, games=len(index["games"]), clips=len(index["clips"]))
    return index


def should_delete_source(index: dict) -> bool:
    """분석이 끝난 원본을 지워도 되는가: 사용자가 골랐고, 게임 풀영상이 하나 이상 저장됐을 때만(plan-fullvideo.md §3.7).

    클립이 아니라 풀영상 기준이다 - 수동 저장 모드는 클립을 안 자르고, 풀영상이 없으면 원본이 유일한 복사본이다.
    """
    return bool(index.get("deleteSourceOnSuccess")) and any(g.get("fullVideo") for g in index.get("games") or [])


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


def _remove_stale_games(games_dir: Path, vod: str, keep: set[str]) -> None:
    """이번 분석으로 다시 만들어지지 않은 이 영상의 옛 게임 폴더(게임 수가 줄었거나 연습 모드로 빠진 게임)를 지운다."""
    try:
        folders = [p for p in games_dir.glob(f"vod_{vod}_g*") if p.is_dir() and p.name not in keep]
    except OSError:
        return
    for folder in folders:
        shutil.rmtree(folder, ignore_errors=True)


def _keep_pinned(folder: Path, data: dict) -> dict:
    try:
        old = json.loads((folder / GAME_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return data
    return {**data, "pinned": True} if isinstance(old, dict) and old.get("pinned") else data


def _make_clips(
    video_path: Path,
    cfg: Config,
    ffmpeg_path: Path,
    root: Path,
    games_root: Path,
    index: dict,
    states: list[FrameState],
    info,
    find_result: FindResult,
    find_portraits: FindPortraits,
    cancel: threading.Event | None,
    report: Callable[..., None],
    place: ClipPlacement,
) -> None:
    """게임마다 풀영상(`games/<키>/full.mp4`)과 `game.json` 을 만들고, `clip.saveMode` 가 auto 면 후보를 클립으로도 자른다.

    새 클립은 스테이징 폴더에 만들고, 다 만든 뒤에만 기존 클립을 지우고 실제 위치로 옮긴다. 수동 저장 모드에서는 사용자가 이미
    저장한 옛 클립을 지우지 않고 같은 ID 의 후보에 저장됨으로 이어 준다. 취소되거나 실패하면 스테이징과 이번에 새로 만든 게임
    폴더만 지우고 기존 것은 그대로 둔다(docs/plan-ui.md §0-(6))."""
    vod = index["id"]
    duration = info.duration_sec
    save_mode = cfg.clip.save_mode
    source = VodSource(
        vod_id=vod, path=video_path, streamer=index.get("streamer"), width=info.width, height=info.height,
        duration_sec=duration, size_bytes=index.get("size") or video_path.stat().st_size,
    )
    spans = [
        s for s in split_games(states, max_gap_sec=cfg.vod.game_gap_sec, min_game_sec=cfg.vod.min_game_sec)
        if not s.practice
    ]
    detections = detect_games(states, spans)
    old_paths = _existing_clip_paths(root, vod)
    olds = load_metas(old_paths)
    old_ids = {p.stem for p in old_paths}
    keep_old = save_mode == "manual"
    staging = place.staging_base / uuid.uuid4().hex
    thumbs = staging / ".thumbs"
    games: list[dict] = []
    clip_ids: list[str] = []
    pending_games: list[tuple[Path, dict]] = []
    new_folders: list[Path] = []
    full_ends: list[float] = []
    n = max(1, len(detections))

    # 컷 단계 진행률을 게임 수가 아니라 컷 수(게임마다 풀영상 1 + 클립 수)에 비례하게 하려고 미리 계획을 전부
    # 세운다(plan-backfill.md B8 - 클립이 몰린 게임 하나 처리하는 동안 막대가 멈춘 듯
    # 보이던 문제, 2026-09-27). apply_filter/_plan_clips 는 이미 계산된 interval 을
    # 훑을 뿐 I/O 가 없어 두 번 부르는 대신 여기서 한 번만 계산해 재사용한다.
    named_by_game = [
        name_vod_candidates(
            _plan_clips(
                apply_filter(det.detection.intervals, cfg.filter, game_mode=det.detection.game_mode), cfg.clip,
                game_mode=det.detection.game_mode,
            ),
            vod, det.span.index, duration=duration,
        )
        for det in detections
    ]
    planned_clips = 0 if keep_old else sum(len(c) for c in named_by_game)
    total_clips = max(1, planned_clips + len(detections))
    base = DECODE_SHARE + GAMES_SHARE
    cut_share = 1.0 - base
    clips_done = 0

    def progress_fraction(games_done: int) -> float:
        """디코드 이후 진행률. 이미 자른 컷(`clips_done`)은 게임이 넘어가도 절대 줄지 않는다.

        "게임 정리"(결과 화면 판독) 단계를 `games_done/n` 만으로만 계산하면, 클립이 몰린 게임
        하나를 다 자른 뒤 다음 게임 정리로 넘어가는 순간 막대가 앞 게임에서 쌓인 클립 진행률을
        무시하고 뚝 떨어져 보인다(실사용 보고, 2026-09-29 - 85%까지 갔다가 24%로 떨어짐:
        `게임 정리` 리포트가 `클립 만들기` 가 이미 반영한 `clips_done` 을 무시했었다). 게임
        진행(`games_done`)과 컷 진행(`clips_done`)을 더해서 절대 역행하지 않게 한다.
        """
        return DECODE_SHARE + GAMES_SHARE * games_done / n + cut_share * clips_done / total_clips

    try:
        for i, det in enumerate(detections):
            if cancel is not None and cancel.is_set():
                raise VodCancelled()
            span = det.span
            report("games", progress_fraction(i), f"게임 {span.index} 결과 화면", games=len(games), clips=len(clip_ids))
            next_start = spans[i + 1].start if i + 1 < len(spans) else None
            result = _safe_result(find_result, video_path, span, next_start)
            result_image = _save_result_image(result, thumbs / f"{vod}_g{span.index:02d}_result.jpg", staging)
            portraits = _safe_portraits(find_portraits, video_path, span)
            portrait_paths = _save_vod_portrait_images(portraits, vod, span.index, thumbs, staging)

            key = vod_game_key(vod, span.index)
            folder = games_root / key
            if not (folder / GAME_JSON).exists():
                new_folders.append(folder)
            full_start, full_end = vod_game_range(
                span, result_at=result.t if result is not None else None, prev_end=full_ends[-1] if full_ends else None,
                next_start=effective_start(spans[i + 1]) if i + 1 < len(spans) else None, duration=duration,
            )
            full_ends.append(full_end)
            report("full", progress_fraction(i), f"게임 {span.index} 풀영상", games=len(games), clips=len(clip_ids))
            full = cut_vod_full_video(
                video_path, full_start, full_end, folder, ffmpeg_path=ffmpeg_path, include_audio=cfg.clip.include_audio,
                source_size=source.size_bytes, source_duration=duration,
            )
            clips_done += 1

            candidates = named_by_game[i]
            to_save = plans_to_save(
                candidates, save_mode, full.video is not None, is_certain=lambda c: is_certain(c.aggregated.tags)
            )
            saved_ids: dict[str, str] = {c.candidate_id: c.clip_id for c in candidates if keep_old and c.clip_id in old_ids}
            game_clip_ids: list[str] = []
            for cand in to_save:
                if cand.clip_id in saved_ids:
                    continue
                if cancel is not None and cancel.is_set():
                    raise VodCancelled()
                rng = cand.plan.range
                clip_id = cand.clip_id
                clip_path = staging / f"{clip_id}.mp4"
                report("cut", progress_fraction(i + 1), f"게임 {span.index} 클립 {len(game_clip_ids) + 1}",
                       games=len(games), clips=len(clip_ids))
                clips_done += 1
                clip_uid = new_clip_uid()
                cut = cut_vod_clip(
                    video_path, rng, clip_path, ffmpeg_path=ffmpeg_path, include_audio=cfg.clip.include_audio,
                    clip_uid=clip_uid,
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
                aggregated = cand.aggregated
                meta = build_vod_metadata(
                    title=cand.title,
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
                    clip_uid=clip_uid,
                )
                clip_path.with_suffix(".json").write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                saved_ids[cand.candidate_id] = clip_id
                game_clip_ids.append(clip_id)
                clip_ids.append(clip_id)

            result_file, portrait_files = save_game_assets(folder, result, portraits, game_mode=det.detection.game_mode)
            data = vod_game_dict(
                source=source, span=span, game_mode=det.detection.game_mode, detection=det.detection,
                candidates=candidates, saved_ids=saved_ids, full_start=full_start, full_end=full_end,
                full=full.video, error=full.error, result=result, result_file=result_file, portraits=portrait_files,
                save_mode=save_mode, cfg=cfg,
            )
            pending_games.append((folder, data))
            games.append({
                "index": span.index, "gameKey": key, "startSec": span.start, "endSec": span.end,
                "fullStartSec": full_start, "fullEndSec": full_end, "fullVideo": full.video is not None,
                "confidence": span.confidence,
                "kFinal": det.detection.k_final, "aFinal": det.detection.a_final,
                "gameMode": det.detection.game_mode,
                "result": match_result_dict(result, result_image), "clipIds": list(saved_ids.values()),
            })
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        for folder in new_folders:
            shutil.rmtree(folder, ignore_errors=True)
        raise

    if not clip_ids and not any(g["fullVideo"] for g in games) and old_paths:
        shutil.rmtree(staging, ignore_errors=True)
        for folder in new_folders:
            shutil.rmtree(folder, ignore_errors=True)
        raise VodAnalyzeError("다시 만들었지만 이 영상에서 게임을 찾지 못했습니다. 기존 결과를 그대로 둡니다")

    report_labels = {"migrated": 0, "conflicts": 0}
    if not keep_old:
        report_labels = migrate_labels(olds, [staging / f"{cid}.json" for cid in clip_ids])
        archive_dir = archive_dir_for(root)
        for meta_path in old_paths:
            delete_clip(
                meta_path, mode=cfg.ui.delete_mode, archive_dir=archive_dir,
                video=find_video_for(meta_path, place.video_roots),
            )
    commit_staged_clips(staging, root, place.video_dir)

    for folder, data in pending_games:
        write_vod_game(folder, _keep_pinned(folder, data))
    _remove_stale_games(games_root, vod, {g["gameKey"] for g in games})

    index.update(
        games=games,
        clips=sorted({cid for g in games for cid in g["clipIds"]}) if keep_old else clip_ids,
        labelsMigrated=report_labels["migrated"], labelConflicts=report_labels["conflicts"],
    )
