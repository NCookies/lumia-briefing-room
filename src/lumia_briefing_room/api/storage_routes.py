"""저장 위치 API: 지금 구조 조회, "새 구조로 옮기기"/저장 폴더 바꾸기(영상만 옮김), 되돌리기. (plan-fullvideo.md §3.10)"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException

from lumia_briefing_room import activity
from lumia_briefing_room.config import Config, PathsConfig, resolve_paths, suggested_root, uses_legacy_layout
from lumia_briefing_room.disk_identity import same_disk
from lumia_briefing_room.pipeline.disk_space import GB, free_bytes_at
from lumia_briefing_room.pipeline.storage_migrate import (
    StorageMoveError,
    execute_storage_move,
    plan_storage_move,
    previous_paths,
    undo_storage_move,
)
from lumia_briefing_room.steam_paths import resolve_recording_root

log = logging.getLogger("lumia_briefing_room.storage")

LEDGER_NAME = "storage_migration.jsonl"


def _free_gb(folder: Path) -> float | None:
    try:
        return round(free_bytes_at(folder) / GB, 1)
    except OSError:
        return None


def _on_recording_disk(folder: Path, recording_root: Path | None) -> bool:
    """녹화와 같은 물리 디스크면 게임이 끝날 때마다 스팀 녹화와 디스크를 다툰다(복사 속도는 제한하지만 느려진다)."""
    if recording_root is None:
        return False
    try:
        return same_disk(folder, recording_root)
    except OSError:
        return False


def register_storage_routes(
    app: FastAPI, *, lock, current_config: Callable[[], Config], put_config: Callable[[dict], dict]
) -> None:
    move_job: dict = {"state": "idle", "doneBytes": 0, "totalBytes": 0, "moved": 0, "message": ""}

    def ledger() -> Path:
        return resolve_paths(current_config().paths).library_steam.parent / LEDGER_NAME

    @app.get("/api/storage")
    def get_storage():
        cfg = current_config()
        resolved = resolve_paths(cfg.paths)
        legacy = uses_legacy_layout(cfg.paths)
        recording = resolve_recording_root(cfg.paths.steam_recording)
        return {
            "layout": "legacy" if legacy else "new",
            "root": None if cfg.paths.root is None else str(cfg.paths.root),
            "fullVideos": None if cfg.paths.full_videos is None else str(cfg.paths.full_videos),
            "suggestedRoot": None if (s := suggested_root(cfg.paths)) is None else str(s),
            "resolved": {
                "clips": str(resolved.clip_roots[0]) if not legacy else str(resolved.clips_steam),
                "fullVideos": str(resolved.games_steam.parent if not legacy else resolved.games_steam),
                "library": str(resolved.library_steam.parent),
                "proxyCache": str(resolved.proxy_cache),
            },
            "legacy": {
                "clips": str(resolved.clips_steam), "vodClips": str(resolved.clips_vod), "games": str(resolved.games_steam),
            },
            "freeGb": {
                "clips": _free_gb(resolved.clips_steam), "fullVideos": _free_gb(resolved.games_steam),
            },
            "canUndo": ledger().is_file(),
            "recordingSameDisk": {
                "clips": _on_recording_disk(resolved.clips_steam, recording),
                "fullVideos": _on_recording_disk(resolved.games_steam, recording),
            },
        }

    @app.post("/api/storage/migrate", status_code=202)
    def migrate(body: dict):
        raw_root = str(body.get("root") or "").strip()
        raw_full = str(body.get("fullVideos") or "").strip()
        if not raw_root:
            raise HTTPException(400, "저장 폴더를 지정해야 합니다")
        if move_job["state"] == "running" or activity.registry.snapshot() or app.state.analysis_queue.busy():
            raise HTTPException(409, "다른 작업을 하는 중에는 저장 위치를 바꿀 수 없습니다. 끝난 뒤 다시 시도하세요")
        cfg = current_config()
        old = resolve_paths(cfg.paths)
        target = PathsConfig(root=Path(raw_root), full_videos=Path(raw_full) if raw_full else None)
        try:
            plan = plan_storage_move(old, resolve_paths(target))
        except StorageMoveError as exc:
            raise HTTPException(409, str(exc))
        previous = previous_paths(cfg.paths)
        move_job.update(state="running", doneBytes=0, totalBytes=plan.total_bytes, moved=0, message="")

        def progress(done: int, total: int) -> None:
            move_job.update(doneBytes=done, totalBytes=total)

        def run() -> None:
            try:
                with lock:
                    moved = execute_storage_move(plan, ledger(), previous=previous, progress=progress)
                    put_config({"paths": {
                        "root": str(target.root), "fullVideos": str(target.full_videos) if target.full_videos else None,
                        "clips": None, "vodClips": None, "games": None,
                    }})
                move_job.update(state="done", moved=moved)
            except (OSError, StorageMoveError) as exc:
                move_job.update(
                    state="error",
                    message=f"옮기는 중 실패했습니다. 남은 파일은 기존 위치에 있으니 다시 시도하세요: {exc}",
                )
            except Exception as exc:
                log.exception("저장 위치 이동 실패")
                move_job.update(state="error", message=str(exc))

        threading.Thread(target=run, daemon=True).start()
        return dict(move_job)

    @app.get("/api/storage/migrate")
    def migrate_status():
        return dict(move_job)

    @app.post("/api/storage/undo")
    def undo():
        if move_job["state"] == "running" or activity.registry.snapshot() or app.state.analysis_queue.busy():
            raise HTTPException(409, "다른 작업을 하는 중에는 되돌릴 수 없습니다")
        with lock:
            try:
                previous = undo_storage_move(ledger())
            except StorageMoveError as exc:
                raise HTTPException(409, str(exc))
            if previous is None:
                return {"restored": False}
            put_config({"paths": previous})
        move_job.update(state="idle", doneBytes=0, totalBytes=0, moved=0, message="")
        return {"restored": True}
