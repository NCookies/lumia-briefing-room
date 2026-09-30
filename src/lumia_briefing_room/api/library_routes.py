"""클립 정리 탭 API: 클립 폴더를 실제 폴더 구조 그대로 보여 주고 폴더를 만들고 이름을 바꾸고 옮기고 지운다. (plan-fullvideo.md §3.9)

앱은 분류하지 않는다. 폴더 조작은 탐색기에서 하는 것과 같은 일이고, 클립 정보는 영상 안 태그·지문으로 이어지므로 어느 쪽에서 옮겨도 그대로다.
경로는 전부 클립 폴더 기준 상대 경로(`/` 구분)이며 클립 폴더 밖으로 나가는 경로는 거부한다(`pipeline/library_fs.py`).
"""

from __future__ import annotations

import functools
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException

from lumia_briefing_room.api.clip_index import norm as _norm, summaries_by_video as _summaries_by_video
from lumia_briefing_room.api.clips import ClipSummary
from lumia_briefing_room.api.export import export_video
from lumia_briefing_room.config import Config, resolve_paths, uses_legacy_layout
from lumia_briefing_room.pipeline.cleanup_registry import registry as cleanup_preview_registry
from lumia_briefing_room.pipeline.delete_helper import PERMANENT, delete_clip, permanently_delete, send_to_recycle_bin
from lumia_briefing_room.pipeline.game_records import records_dir_for
from lumia_briefing_room.pipeline.label_archive import archive_dir_for
from lumia_briefing_room.pipeline.library_fs import LibraryError, LibraryRoots
from lumia_briefing_room.pipeline.proxy import proxy_file


def _roots(cfg: Config) -> LibraryRoots:
    resolved = resolve_paths(cfg.paths)
    if uses_legacy_layout(cfg.paths):
        return LibraryRoots([("스팀 녹화", resolved.clips_steam), ("영상 파일", resolved.clips_vod)], single=False)
    return LibraryRoots([("클립", resolved.clips_root)], single=True)


def register_library_routes(
    app: FastAPI,
    *,
    lock,
    current_config: Callable[[], Config],
    put_config: Callable[[dict], dict],
    serialize: Callable[[ClipSummary], dict],
) -> None:
    def roots() -> LibraryRoots:
        return _roots(current_config())

    summaries_by_video = _summaries_by_video

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

    def crumbs(lib: LibraryRoots, rel: str) -> list[dict]:
        names = [p for p in rel.split("/") if p]
        result = [{"name": lib.entries[0][0] if lib.single else "클립 폴더", "rel": ""}]
        for i, name in enumerate(names):
            result.append({"name": name, "rel": "/".join(names[: i + 1])})
        return result

    @app.get("/api/library")
    @guarded
    def get_library(path: str = ""):
        cfg = current_config()
        lib = _roots(cfg)
        with lock:
            folders, videos = lib.list_folder(path)
            mapping = summaries_by_video(cfg, {_norm(v) for v in videos})
            clips = []
            for video in videos:
                clip = mapping.get(_norm(video))
                if clip is None:
                    continue
                clips.append({**serialize(clip), "relPath": lib.rel_of(video), "fileName": video.name})
        return {
            "path": "/".join(p for p in path.split("/") if p),
            "layout": "new" if lib.single else "legacy",
            "virtualTop": lib.is_virtual(path),
            "crumbs": crumbs(lib, path),
            "folders": folders,
            "clips": clips,
        }

    @app.post("/api/library/folders", status_code=201)
    @guarded
    def create_folder(body: dict):
        with lock:
            return {"path": roots().make_folder(str(body.get("path") or ""), str(body.get("name") or ""))}

    @app.patch("/api/library/rename")
    @guarded
    def rename(body: dict):
        with lock:
            new = roots().rename(str(body.get("path") or ""), str(body.get("name") or ""))
        cleanup_preview_registry.notify_clips_changed()
        return {"path": new}

    @app.post("/api/library/move")
    @guarded
    def move(body: dict):
        items = [str(i) for i in body.get("items") or []]
        if not items:
            raise HTTPException(400, "옮길 항목을 골라야 합니다")
        with lock:
            moved = roots().move(items, str(body.get("dest") or ""))
        cleanup_preview_registry.notify_clips_changed()
        return {"moved": moved}

    @app.post("/api/library/delete")
    @guarded
    def delete(body: dict):
        items = [str(i) for i in body.get("items") or []]
        if not items:
            raise HTTPException(400, "지울 항목을 골라야 합니다")
        cfg = current_config()
        lib = _roots(cfg)
        resolved = resolve_paths(cfg.paths)
        mode = cfg.ui.delete_mode
        remove = permanently_delete if mode == PERMANENT else send_to_recycle_bin
        with lock:
            for rel in items:
                lib.ensure_entry(rel)
            targets = [(rel, lib.resolve(rel)) for rel in items]
            videos = lib.collect_videos(items)
            mapping = summaries_by_video(cfg, {_norm(v) for v in videos})
            users: dict[str, int] = {}
            for clip in mapping.values():
                users[_norm(clip.meta_path)] = users.get(_norm(clip.meta_path), 0) + 1
            deleted = 0
            for video in videos:
                clip = mapping.get(_norm(video))
                proxy = proxy_file(resolved.proxy_cache, clip.id) if clip else None
                if clip is None or users.get(_norm(clip.meta_path), 0) > 1:
                    remove([p for p in (video, proxy) if p is not None and p.exists()])
                else:
                    library = clip.meta_path.parent
                    keep_records = cfg.retention.keep_game_records and library == resolved.library_steam
                    delete_clip(
                        clip.meta_path, mode=mode, archive_dir=archive_dir_for(library),
                        records_dir=records_dir_for(library) if keep_records else None,
                        proxy=proxy if proxy is not None and proxy.exists() else None, video=video,
                    )
                deleted += 1
            for _, path in targets:
                if path.is_dir():
                    remove([path])
        cleanup_preview_registry.notify_clips_changed()
        return {"deleted": deleted}

    @app.post("/api/library/reveal")
    @guarded
    def reveal(body: dict):
        path = roots().resolve(str(body.get("path") or ""))
        if not path.exists():
            raise HTTPException(404, "찾을 수 없습니다")
        if os.name != "nt":
            raise HTTPException(501, "탐색기 열기는 Windows 에서만 됩니다")
        args = ["explorer", f"/select,{path}"] if path.is_file() else ["explorer", str(path)]
        subprocess.Popen(args)
        return {"opened": str(path)}

    @app.post("/api/library/export")
    @guarded
    def export(body: dict):
        items = [str(i) for i in body.get("items") or []]
        directory = Path(str(body.get("dir") or ""))
        if not items:
            raise HTTPException(400, "내보낼 항목을 골라야 합니다")
        if not directory.is_dir():
            raise HTTPException(404, "저장할 폴더를 찾을 수 없습니다")
        with lock:
            videos = roots().collect_videos(items)
            saved = [str(export_video(v, directory, v.stem)) for v in videos]
        put_config({"paths": {"exportDefault": str(directory)}})
        return {"paths": saved}
