"""풀영상 자동 정리. (plan-fullvideo.md §3.5)

대상은 `games/<경기키>/full.mp4` 이다. 저장한 클립은 대상이 아니다(사용자가 남기겠다고 고른 것).
풀영상만 지우고 `game.json`(결과·후보·마커·수정 기록)과 결과·초상화 이미지는 남긴다.
선정 규칙(나이·개수·용량 한도, 고정·보호 태그)은 클립 정리와 같은 `select_for_auto_clean` 을 쓴다.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lumia_briefing_room.config import RetentionConfig
from lumia_briefing_room.pipeline.delete_helper import PERMANENT, permanently_delete, send_to_recycle_bin
from lumia_briefing_room.pipeline.game_store import FULL_VIDEO, GAME_JSON
from lumia_briefing_room.pipeline.preserve_before_delete import candidates_to_preserve
from lumia_briefing_room.pipeline.retention import select_for_auto_clean

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GameCleanupPlan:
    to_delete: list[Path]  # 풀영상을 지울(지운) 게임 폴더
    bytes_to_free: int
    preserve_clips: int = 0  # 지우기 전에 클립으로 남길(남긴) 후보 수 - `retention.preserveBeforeDelete` 가 켜졌을 때만
    held_back: list[Path] = field(default_factory=list)  # 클립을 못 남겨 이번엔 지우지 않은 폴더


def _parse_utc(text) -> datetime | None:
    if not isinstance(text, str):
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


GamesDirs = Path | Sequence[Path]


def _as_dirs(games_dirs: GamesDirs) -> list[Path]:
    return [games_dirs] if isinstance(games_dirs, Path) else list(games_dirs)


def _entries(games_dirs: GamesDirs) -> list[dict]:
    folders: list[Path] = []
    for games_dir in _as_dirs(games_dirs):
        try:
            folders += sorted(p for p in games_dir.iterdir() if p.is_dir())
        except OSError:
            continue
    entries = []
    for folder in folders:
        video = folder / FULL_VIDEO
        try:
            data = json.loads((folder / GAME_JSON).read_text(encoding="utf-8"))
            size = video.stat().st_size
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        created = _parse_utc(data.get("matchStartUtc")) or datetime.fromtimestamp(video.stat().st_mtime, timezone.utc)
        tags: set[str] = set()
        for cand in data.get("candidates") or []:
            tags.update(cand.get("tags") or [])
        entries.append(
            {
                "pinned": bool(data.get("pinned")),
                "tags": sorted(tags),
                "_created_at": created,
                "_size_bytes": size,
                "_path": folder,
                "_key": folder.name,
                "_preserve": len(candidates_to_preserve(data)),
            }
        )
    return entries


def plan_game_cleanup(games_dir: GamesDirs, cfg: RetentionConfig, *, now: datetime | None = None) -> GameCleanupPlan:
    now = now or datetime.now(timezone.utc)
    if not cfg.auto_clean_enabled:
        return GameCleanupPlan([], 0)
    selected = select_for_auto_clean(_entries(games_dir), cfg, now=lambda: now)
    preserve = sum(e["_preserve"] for e in selected) if cfg.preserve_before_delete else 0
    return GameCleanupPlan([e["_path"] for e in selected], sum(e["_size_bytes"] for e in selected), preserve)


def game_cleanup_preview(games_dir: GamesDirs, cfg: RetentionConfig, *, now: datetime | None = None) -> dict[str, dict]:
    """다음 자동 정리 때 풀영상이 지워질 게임의 이유·예정 시각(경기 키 기준). 실제 정리와 같은 선정 함수를 쓴다."""
    now = now or datetime.now(timezone.utc)
    if not cfg.auto_clean_enabled:
        return {}
    selected = select_for_auto_clean(_entries(games_dir), cfg, now=lambda: now)
    preview: dict[str, dict] = {}
    for e in selected:
        due_at = None
        if e["_reason"] == "age" and cfg.max_age_days is not None:
            due_at = (e["_created_at"] + timedelta(days=cfg.max_age_days)).isoformat().replace("+00:00", "Z")
        preview[e["_key"]] = {
            "reason": e["_reason"],
            "dueAt": due_at,
            "preserveCount": e["_preserve"] if cfg.preserve_before_delete else 0,
        }
    return preview


def delete_full_video(folder: Path, *, mode: str) -> None:
    """풀영상 파일만 지우고 게임 기록에 지운 사실을 남긴다."""
    video = folder / FULL_VIDEO
    if mode == PERMANENT:
        permanently_delete([video])
    else:
        send_to_recycle_bin([video])
    path = folder / GAME_JSON
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    data["deletedFullVideo"] = data.get("fullVideo")
    data["fullVideo"] = None
    data["fullVideoDeletedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def run_game_cleanup(
    games_dir: GamesDirs, cfg: RetentionConfig, *, now: datetime | None = None, preserve: Callable[[Path], bool] | None = None
) -> GameCleanupPlan:
    """`preserve(폴더)` 는 지우기 직전 남길 클립을 저장하고 성공 여부를 돌려준다. 보존이 켜졌는데 `preserve` 가
    없거나 실패하면 그 풀영상은 지우지 않는다."""
    plan = plan_game_cleanup(games_dir, cfg, now=now)
    deleted: list[Path] = []
    held: list[Path] = []
    freed = 0
    for folder in plan.to_delete:
        if cfg.preserve_before_delete and not (preserve is not None and preserve(folder)):
            held.append(folder)
            continue
        try:
            size = (folder / FULL_VIDEO).stat().st_size
            delete_full_video(folder, mode=cfg.delete_mode)
        except OSError:
            log.exception("풀영상을 지우지 못했다: %s", folder)
            continue
        deleted.append(folder)
        freed += size
    if deleted or held:
        from lumia_briefing_room.pipeline.cleanup_registry import registry

        registry.notify_clips_changed()
    return GameCleanupPlan(deleted, freed, plan.preserve_clips, held)
