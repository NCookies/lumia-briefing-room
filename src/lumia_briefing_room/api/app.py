"""로컬 전용 FastAPI 앱. (plan-ui.md §2) 127.0.0.1 에만 바인드해서 쓴다(SPEC §3)."""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from lumia_briefing_room.api.clips import find_clip, scan_clips, to_summary_dict
from lumia_briefing_room.api.filters import ClipQuery, filter_clip_summaries, sort_clip_summaries
from lumia_briefing_room.config import (
    Config,
    dataclass_from_camel_dict,
    dataclass_to_camel_dict,
    resolve_paths,
    save_config,
)
from lumia_briefing_room.pipeline.retention import restore_clip, trash_clip


def _deep_merge(base: dict, overrides: dict) -> dict:
    """overrides 를 base 위에 재귀적으로 얹는다. 없는 키는 base 값을 그대로 둔다."""
    result = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _serialize(clip_summary) -> dict:
    meta = dict(clip_summary.meta)
    meta["id"] = clip_summary.id
    return meta


def _clips_dir(app: FastAPI) -> Path:
    return resolve_paths(app.state.config.paths).clips


def create_app(cfg: Config, *, config_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="Lumia Briefing Room API")
    app.state.config = cfg
    app.state.config_path = config_path

    @app.get("/api/clips")
    def list_clips(
        tags: str = "",
        dayNight: str | None = None,
        gameMode: str | None = None,
        pinned: bool = False,
        trashed: bool = False,
        minPvpScore: float | None = None,
        label: str | None = None,
        sort: str | None = None,
    ):
        clips_dir = _clips_dir(app)
        source = (clips_dir / ".trash") if trashed else clips_dir
        summaries = scan_clips(source)
        query = ClipQuery(
            tags=[t for t in tags.split(",") if t],
            day_night=dayNight,
            game_mode=gameMode,
            pinned_only=pinned,
            trashed_only=trashed,
            min_pvp_score=minPvpScore,
            label=label,
        )
        filtered = sort_clip_summaries(filter_clip_summaries(summaries, query), sort)
        return [_serialize(c) for c in filtered]

    @app.get("/api/clips/{clip_id}")
    def get_clip(clip_id: str):
        clip = find_clip(_clips_dir(app), clip_id) or find_clip(_clips_dir(app) / ".trash", clip_id)
        if clip is None:
            raise HTTPException(404, "클립을 찾을 수 없다")
        return _serialize(clip)

    @app.patch("/api/clips/{clip_id}")
    def patch_clip(clip_id: str, body: dict):
        clips_dir = _clips_dir(app)
        clip = find_clip(clips_dir, clip_id)
        if clip is None:
            raise HTTPException(404, "클립을 찾을 수 없다")
        if "userLabel" in body and body["userLabel"] not in (None, "pvp", "pve"):
            raise HTTPException(400, "userLabel 은 pvp / pve / null 만 가능하다")
        meta = {**clip.meta, **{k: v for k, v in body.items() if k in ("title", "pinned", "userLabel")}}
        clip.meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta | {"id": clip_id}

    @app.post("/api/clips/{clip_id}/trash")
    def trash(clip_id: str):
        clip = find_clip(_clips_dir(app), clip_id)
        if clip is None:
            raise HTTPException(404, "클립을 찾을 수 없다")
        trash_dir = _clips_dir(app) / ".trash"
        trash_clip(clip.meta_path, trash_dir)
        return {"id": clip_id, "trashed": True}

    @app.post("/api/clips/{clip_id}/restore")
    def restore(clip_id: str):
        clips_dir = _clips_dir(app)
        clip = find_clip(clips_dir / ".trash", clip_id)
        if clip is None:
            raise HTTPException(404, "휴지통에 없다")
        restore_clip(clip.meta_path, clips_dir)
        return {"id": clip_id, "trashed": False}

    @app.delete("/api/clips/{clip_id}")
    def delete(clip_id: str):
        clips_dir = _clips_dir(app)
        clip = find_clip(clips_dir / ".trash", clip_id)
        if clip is None:
            raise HTTPException(400, "휴지통에 있는 클립만 완전히 지울 수 있다")
        for f in [clip.meta_path.with_suffix(".mp4"), clip.meta_path]:
            f.unlink(missing_ok=True)
        thumb = clip.meta.get("thumbnailPath")
        if thumb:
            Path(thumb).unlink(missing_ok=True)
        return {"id": clip_id, "deleted": True}

    @app.get("/api/clips/{clip_id}/video")
    def video(clip_id: str, request: Request):
        clip = find_clip(_clips_dir(app), clip_id)
        if clip is None:
            raise HTTPException(404, "클립을 찾을 수 없다")
        return _serve_range(clip.meta_path.with_suffix(".mp4"), request, media_type="video/mp4")

    @app.get("/api/clips/{clip_id}/thumbnail")
    def thumbnail(clip_id: str):
        clip = find_clip(_clips_dir(app), clip_id)
        if clip is None:
            raise HTTPException(404, "클립을 찾을 수 없다")
        thumb = clip.meta.get("thumbnailPath")
        if not thumb or not Path(thumb).exists():
            raise HTTPException(404, "썸네일이 없다")
        return FileResponse(thumb, media_type="image/jpeg")

    @app.get("/api/config")
    def get_config():
        return dataclass_to_camel_dict(app.state.config)

    @app.put("/api/config")
    def put_config(body: dict):
        current = dataclass_to_camel_dict(app.state.config)
        merged = _deep_merge(current, body)
        new_cfg = dataclass_from_camel_dict(Config, merged)
        app.state.config = new_cfg
        if app.state.config_path is not None:
            save_config(new_cfg, app.state.config_path)
        return dataclass_to_camel_dict(new_cfg)

    return app


def _serve_range(path: Path, request: Request, *, media_type: str) -> Response:
    """Range 헤더를 지원하는 파일 응답. (plan-ui.md §2.5 — <video> 탐색바에 필수)"""
    file_size = path.stat().st_size
    range_header = request.headers.get("range")

    if not range_header:
        data = path.read_bytes()
        return Response(
            content=data, media_type=media_type,
            headers={"accept-ranges": "bytes", "content-length": str(file_size)},
        )

    unit, _, range_spec = range_header.partition("=")
    start_s, _, end_s = range_spec.partition("-")
    start = int(start_s) if start_s else 0
    end = int(end_s) if end_s else file_size - 1
    end = min(end, file_size - 1)
    length = end - start + 1

    with open(path, "rb") as f:
        f.seek(start)
        chunk = f.read(length)

    return Response(
        content=chunk,
        status_code=206,
        media_type=media_type,
        headers={
            "accept-ranges": "bytes",
            "content-range": f"bytes {start}-{end}/{file_size}",
            "content-length": str(length),
        },
    )
