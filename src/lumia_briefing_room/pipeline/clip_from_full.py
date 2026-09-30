"""풀영상에서 후보 구간을 잘라 클립으로 저장한다. (plan-fullvideo.md §3.2 "클립 저장(수동)")

원본 세그먼트는 링버퍼가 이미 지웠을 수 있어 풀영상에서 자른다. 풀영상도 `-c copy` 결과라 키프레임(3초 격자)에
붙어 시작이 앞으로 최대 3초 당겨진다. 클립 메타데이터는 기존 클립과 같은 형식이라 기존 화면이 그대로 읽는다.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterable
from pathlib import Path

from lumia_briefing_room.config import Config
from lumia_briefing_room.pipeline.clip import make_thumbnail
from lumia_briefing_room.pipeline.clip_assets import stored_asset_path
from lumia_briefing_room.pipeline.clip_files import find_video, find_video_for
from lumia_briefing_room.pipeline.clip_uid import new_clip_uid
from lumia_briefing_room.pipeline.mp4_tags import uid_metadata_args
from lumia_briefing_room.pipeline.game_candidates import effective_range, effective_title
from lumia_briefing_room.pipeline.game_store import FULL_VIDEO
from lumia_briefing_room.detect.pvp import PvpScore
from lumia_briefing_room.detect.types import CombatInterval
from lumia_briefing_room.pipeline.clip import ClipRange
from lumia_briefing_room.pipeline.metadata import ClipMetadata, phase_index, revive_cost, write_metadata
from lumia_briefing_room.pipeline.vod_clips import build_vod_metadata
from lumia_briefing_room.procs import run_hidden

PORTRAIT_SLOTS = ("me", "teammate1", "teammate2")
_KEPT_ON_REPLACE = ("title", "userLabel", "labelSource", "labelConflict", "pinned", "deletedAt", "clipUid", "memo")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class FullVideoMissing(Exception):
    """풀영상이 없다(자동 정리로 지워졌거나 만들지 못했다)."""


def _unique_clip_id(clips_dir: Path, wanted: str, video_roots: Iterable[Path] = ()) -> str:
    roots = tuple(video_roots)
    clip_id, n = wanted, 1
    while (clips_dir / f"{clip_id}.json").exists() or find_video(clips_dir, clip_id, roots) is not None:
        n += 1
        clip_id = f"{wanted}-r{n}"
    return clip_id


def _run_ffmpeg(cmd: list[str]) -> None:
    run_hidden(cmd, check=True, capture_output=True)


def cut_from_full(full: Path, out: Path, start: float, end: float, *, ffmpeg_path: Path, clip_uid: str | None = None) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(ffmpeg_path), "-hide_banner", "-v", "error", "-y",
        "-ss", f"{start:.3f}", "-i", str(full), "-t", f"{end - start:.3f}",
        "-map", "0", "-c", "copy", *(uid_metadata_args(clip_uid) if clip_uid else []), str(out),
    ]
    _run_ffmpeg(cmd)


def _copy_asset(src: Path, dest: Path) -> bool:
    if dest.exists():
        return True
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    except OSError:
        return False
    return True


def _assets_for_clip(game: dict, game_folder: Path, thumbnails_root: Path, clips_root: Path) -> tuple[dict | None, str | None, list[str]]:
    """게임 폴더의 결과·초상화 이미지를 클립이 읽는 위치(.thumbs)로 복사해 클립 상대 경로를 돌려준다."""
    key = game["gameKey"]
    result = game.get("matchResult")
    if isinstance(result, dict) and result.get("imagePath"):
        target = thumbnails_root / f"{key}_result.jpg"
        if _copy_asset(game_folder / result["imagePath"], target):
            result = {**result, "imagePath": stored_asset_path(target, clips_root)}
        else:
            result = {k: v for k, v in result.items() if k != "imagePath"}
    portraits = game.get("portraits") or {}
    paths: dict[str, str | None] = {}
    for slot in PORTRAIT_SLOTS:
        name = portraits.get(slot)
        target = thumbnails_root / f"{key}_portrait_{slot}.jpg"
        paths[slot] = stored_asset_path(target, clips_root) if name and _copy_asset(game_folder / name, target) else None
    return result, paths["me"], [p for p in (paths["teammate1"], paths["teammate2"]) if p]


def _vod_clip_metadata(
    game: dict, cand: dict, *, start: float, end: float, offset: float, thumb_rel: str | None,
    result: dict | None, me_portrait: str | None, mates: list[str],
) -> dict:
    """영상 파일 게임에서 저장한 클립: 영상 클립과 같은 형식(vodId·원본 안 위치)이라 영상 클립 화면·API 가 그대로 읽는다.
    풀영상 0초 = 원본 영상 안 `vodStartSec` 라서 원본 안 위치 = `vodStartSec`(= offsetSec) + 풀영상 안 시각."""
    interval = CombatInterval(
        start=offset + float(cand.get("combatStart", start)), end=offset + float(cand.get("combatEnd", end)),
        tags=frozenset(cand.get("tags") or []), k_delta=int(cand.get("killDelta") or 0),
        a_delta=int(cand.get("assistDelta") or 0), died=bool(cand.get("died")), day_night=cand.get("dayNight"),
        confidence=float(cand.get("detectorConfidence") or 0.0), region=cand.get("region"), game_day=cand.get("gameDay"),
        enemy_ring_mean=cand.get("enemyRingMean"), ultimate_delta=cand.get("ultimateDelta"),
        cobalt_phase=cand.get("cobaltPhase"),
    )
    meta = build_vod_metadata(
        title=effective_title(cand), vod_id=game["vodId"], vod_file=game.get("vodFile") or "",
        streamer=game.get("streamer"), game_mode=game.get("gameMode") or "battle_royale",
        game_index=int(game.get("vodGameIndex") or 0),
        game_start=float(game.get("spanStartSec") or offset), game_end=float(game.get("spanEndSec") or offset),
        width=int(game.get("sourceWidth") or 0), height=int(game.get("sourceHeight") or 0), interval=interval,
        clip_range=ClipRange(start=offset + start, end=offset + end, preroll_source=cand.get("prerollSource", "user")),
        duration_sec=end - start, thumbnail_path=thumb_rel,
        pvp=PvpScore(score=float(cand.get("pvpScore") or 0.0), signals=list(cand.get("pvpSignals") or [])),
        match_kills=game.get("matchKills"), match_assists=game.get("matchAssists"), match_result=None,
        result_image_path=None, my_character_portrait_path=me_portrait, teammate_portrait_paths=mates,
    )
    meta["matchResult"] = result
    return meta


def save_candidate_clip(
    game: dict,
    cand: dict,
    *,
    game_folder: Path,
    clips_dir: Path,
    cfg: Config,
    ffmpeg_path: Path,
    thumbnails_root: Path | None = None,
    replace_clip_id: str | None = None,
    video_dir: Path | None = None,
    video_roots: Iterable[Path] = (),
) -> str:
    """후보 하나를 클립으로 저장하고 클립 ID 를 돌려준다. `clips_dir` 는 정보(json·썸네일) 폴더, `video_dir` 는 새 영상이 놓일 폴더(기본 `clips_dir`).
    `replace_clip_id` 가 있으면 그 클립을 새 범위로 교체한다(같은 영상 파일·클립 ID·제목·라벨·고정 상태 유지 - 영상은 `video_roots` 아래
    지금 있는 자리에서 바꾼다)."""
    video = game.get("fullVideo")
    full = game_folder / FULL_VIDEO
    if not video or not full.is_file():
        raise FullVideoMissing(game["gameKey"])
    duration = float(video.get("durationSec") or 0.0)
    start, end = effective_range(cand, duration)
    if end <= start:
        raise ValueError("구간이 올바르지 않습니다")

    roots = tuple(video_roots)
    video_root = video_dir or clips_dir
    thumbnails_root = thumbnails_root or (clips_dir / ".thumbs")
    clip_id = replace_clip_id or _unique_clip_id(clips_dir, cand["id"], roots)
    json_path = clips_dir / f"{clip_id}.json"
    clip_path = (find_video_for(json_path, roots) if replace_clip_id else None) or video_root / f"{clip_id}.mp4"
    old = _read_json(json_path) if replace_clip_id else {}
    uid = old.get("clipUid") or new_clip_uid()
    if replace_clip_id:
        staged = clip_path.with_name(f"{clip_id}.replace.mp4")
        try:
            cut_from_full(full, staged, start, end, ffmpeg_path=ffmpeg_path, clip_uid=uid)
            os.replace(staged, clip_path)
        finally:
            staged.unlink(missing_ok=True)
    else:
        cut_from_full(full, clip_path, start, end, ffmpeg_path=ffmpeg_path, clip_uid=uid)

    thumb_rel = None
    if cfg.encode.thumbnail.enabled:
        thumb = thumbnails_root / f"{clip_id}.jpg"
        make_thumbnail(
            clip_path, thumb, duration_sec=end - start, offset_ratio=cfg.encode.thumbnail.offset_ratio,
            width=cfg.encode.thumbnail.width, ffmpeg_path=ffmpeg_path,
        )
        thumb_rel = stored_asset_path(thumb, clips_dir)

    result, me_portrait, mates = _assets_for_clip(game, game_folder, thumbnails_root, clips_dir)
    offset = float(video.get("offsetSec") or 0.0)
    seg = float(video.get("segmentDurationSec") or 3.0)
    day, night = cand.get("gameDay"), cand.get("dayNight")
    phase = phase_index(day, night) if day is not None and night is not None else None
    combat_start = offset + float(cand.get("combatStart", start))
    combat_end = offset + float(cand.get("combatEnd", end))

    if game.get("source") == "vod":
        vod_meta = _vod_clip_metadata(
            game, cand, start=start, end=end, offset=offset, thumb_rel=thumb_rel, result=result,
            me_portrait=me_portrait, mates=mates,
        )
        vod_meta["clipUid"] = uid
        return _finish(json_path, json.dumps(vod_meta, ensure_ascii=False, indent=2), replace_clip_id, clip_id)

    meta = ClipMetadata(
        title=effective_title(cand),
        session_dir=game.get("sessionDir", ""),
        session_start_utc=game.get("sessionStartUtc", ""),
        match_start_utc=game.get("matchStartUtc", ""),
        game_mode=game.get("gameMode", "battle_royale"),
        source_width=int(game.get("sourceWidth") or 0),
        source_height=int(game.get("sourceHeight") or 0),
        segment_start=int((offset + start) // seg) + 1,
        segment_end=int((offset + end) // seg) + 1,
        video_offset_sec=offset + start,
        duration_sec=end - start,
        thumbnail_path=thumb_rel,
        source_incomplete=bool(video.get("sourceIncomplete")),
        audio_status=video.get("audioStatus", "full"),
        combat_start_offset_sec=combat_start,
        combat_end_offset_sec=combat_end,
        preroll_source=cand.get("prerollSource", "user"),
        tags=list(cand.get("tags") or []),
        kill_delta=int(cand.get("killDelta") or 0),
        assist_delta=int(cand.get("assistDelta") or 0),
        died=bool(cand.get("died")),
        pvp_score=float(cand.get("pvpScore") or 0.0),
        pvp_signals=list(cand.get("pvpSignals") or []),
        team_wipe=None,
        enemy_ring_mean=cand.get("enemyRingMean"),
        ultimate_delta=cand.get("ultimateDelta"),
        region=cand.get("region"),
        user_label=None,
        label_source=None,
        label_conflict=False,
        game_day=day,
        day_night=night,
        cobalt_phase=cand.get("cobaltPhase"),
        phase_index=phase,
        revive_cost=revive_cost(phase) if phase is not None else None,
        my_character=None,
        team_characters=[],
        pinned=False,
        deleted_at=None,
        match_kills=game.get("matchKills"),
        match_assists=game.get("matchAssists"),
        match_team_kills=None,
        detector_confidence=float(cand.get("detectorConfidence") or 0.0),
        match_result=result,
        match_end_utc=game.get("matchEndUtc"),
        clip_uid=uid,
        my_character_portrait_path=me_portrait,
        teammate_portrait_paths=mates,
        match_result_source=None,
    )
    write_metadata(meta, json_path)
    return _merge_kept(json_path, old, clip_id)


def _merge_kept(json_path: Path, old: dict, clip_id: str) -> str:
    if old:
        kept = {k: old[k] for k in _KEPT_ON_REPLACE if k in old}
        merged = {**json.loads(json_path.read_text(encoding="utf-8")), **kept}
        json_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return clip_id


def _finish(json_path: Path, text: str, replace_clip_id: str | None, clip_id: str) -> str:
    old = _read_json(json_path) if replace_clip_id else {}
    json_path.write_text(text, encoding="utf-8")
    return _merge_kept(json_path, old, clip_id)
