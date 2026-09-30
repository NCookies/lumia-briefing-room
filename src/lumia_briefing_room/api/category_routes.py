"""클립 카테고리 API: 목록(첫 클립 썸네일·개수)·만들기·클립 옮기기. (plan-fullvideo.md §3.9)"""

from __future__ import annotations

import functools
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException

from lumia_briefing_room.api.clip_index import light_index, locate_clip, norm
from lumia_briefing_room.config import ARCHIVE_FOLDER, AUTO_ARCHIVE_FOLDER, Config
from lumia_briefing_room.pipeline import categories as cats
from lumia_briefing_room.pipeline.cleanup_registry import registry as cleanup_preview_registry
from lumia_briefing_room.pipeline.clip_files import move_file, walk_videos
from lumia_briefing_room.pipeline.library_fs import LibraryError


def _unique(target: Path) -> Path:
    n = 2
    while True:
        candidate = target.with_name(f"{target.stem} ({n}){target.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def register_category_routes(app: FastAPI, *, lock, current_config: Callable[[], Config]) -> None:
    def guarded(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except LibraryError as exc:
                raise HTTPException(exc.status, str(exc))
            except OSError as exc:
                raise HTTPException(500, f"파일을 다루는 중 오류가 났습니다: {exc}")

        return wrapper

    @app.get("/api/categories")
    @guarded
    def list_categories():
        cfg = current_config()
        if not cats.enabled(cfg):
            return {"enabled": False, "categories": []}
        root = cats.clips_root(cfg)
        with lock:
            for name in (ARCHIVE_FOLDER, AUTO_ARCHIVE_FOLDER):
                (root / name).mkdir(parents=True, exist_ok=True)
            index = light_index(cfg)
            result = []
            for name in cats.category_names(cfg):
                folder = root / name
                videos = list(walk_videos([folder])) if folder.is_dir() else []
                known = [entry for v in videos if (entry := index.get(norm(v))) is not None]
                newest = max(known, key=lambda entry: entry[1], default=None)
                result.append({
                    "name": name, "auto": name == AUTO_ARCHIVE_FOLDER, "default": name == ARCHIVE_FOLDER,
                    "clipCount": len(videos), "thumbnailClipId": newest[0] if newest else None,
                })
        return {"enabled": True, "categories": result}

    @app.post("/api/categories", status_code=201)
    @guarded
    def create_category(body: dict):
        cfg = current_config()
        if not cats.enabled(cfg):
            raise HTTPException(409, "카테고리는 새 저장 폴더 구조에서만 쓸 수 있습니다")
        with lock:
            return {"name": cats.create_category(cfg, body.get("name"))}

    @app.post("/api/categories/move")
    @guarded
    def move_clips(body: dict):
        cfg = current_config()
        if not cats.enabled(cfg):
            raise HTTPException(409, "카테고리는 새 저장 폴더 구조에서만 쓸 수 있습니다")
        ids = [str(i) for i in body.get("clipIds") or []]
        if not ids:
            raise HTTPException(400, "옮길 클립을 골라야 합니다")
        with lock:
            dest = cats.category_folder(cfg, body.get("category"), create=True)
            clips = []
            for clip_id in ids:
                clip = locate_clip(cfg, clip_id)
                if clip is None or not clip.video.is_file():
                    raise HTTPException(404, "클립을 찾을 수 없습니다")
                clips.append(clip)
            moved = 0
            for clip in clips:
                if clip.video.parent.resolve() == dest.resolve():
                    continue
                target = dest / clip.video.name
                move_file(clip.video, _unique(target) if target.exists() else target, overwrite=False)
                moved += 1
        if moved:
            cleanup_preview_registry.notify_clips_changed()
        return {"moved": moved, "category": dest.name}
