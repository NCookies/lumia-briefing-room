"""로컬 전용 FastAPI 앱. (plan-ui.md §2) 127.0.0.1 에만 바인드해서 쓴다(SPEC §3)."""

import functools
import json
import logging
import re
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from lumia_briefing_room import __version__, paths
from lumia_briefing_room.appmode import resolve_mode
from lumia_briefing_room.api.clips import find_clip, scan_clips, to_summary_dict
from lumia_briefing_room.api.export import (
    export_video,
    is_valid_folder_name,
    list_roots,
    list_subdirs,
    parent_of,
)
from lumia_briefing_room.api.onboarding import register_onboarding_routes
from lumia_briefing_room.api.vods import register_vod_routes
from lumia_briefing_room.api.filters import ClipQuery, filter_clip_summaries, sort_clip_summaries
from lumia_briefing_room.config import (
    Config,
    discover_ffmpeg,
    dataclass_from_camel_dict,
    dataclass_to_camel_dict,
    load_config,
    resolve_paths,
    save_config,
)
from lumia_briefing_room.pipeline.game_records import (
    delete_record,
    game_key,
    load_records,
    record_game,
    records_dir_for,
)
from lumia_briefing_room.pipeline.label_archive import archive_dir_for, archive_if_labeled
from lumia_briefing_room.pipeline.cleanup import plan_cleanup, remove_orphan_result_images, run_cleanup
from lumia_briefing_room.pipeline.retention import restore_clip, trash_clip
from lumia_briefing_room.pipeline.reprocess import GameRef, ReprocessError, reprocess_game
from lumia_briefing_room.pipeline.trim import trim_clip, validate_range
from lumia_briefing_room.steam_paths import discover_recording_root


client_log = logging.getLogger("lumia_briefing_room.client")
_CLIENT_LOG_LIMIT = 4000


class ClientLog(BaseModel):
    message: str
    level: str = "error"
    stack: str | None = None
    url: str | None = None
    time: str | None = None


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
    meta["sizeBytes"] = clip_summary.size_bytes
    return meta


def read_boundaries(cfg: Config):
    """Player.log 에서 경기 시작/종료 시각 목록을 읽는다(다시 분석할 게임의 종료 시각을 찾는 데 쓴다)."""
    from datetime import datetime

    from lumia_briefing_room.cli.watch import default_player_log_dir
    from lumia_briefing_room.pipeline.watcher import discover_backlog

    log_dir = cfg.watch.player_log or default_player_log_dir()
    return discover_backlog(
        log_dir / "Player.log", log_dir / "Player-prev.log", local_tz=datetime.now().astimezone().tzinfo
    )


def _unlink(path: Path, *, attempts: int = 5) -> None:
    """Windows 는 다른 요청이 그 파일을 읽는 중이면 지우기가 PermissionError 로 실패한다 — 잠깐 기다려 다시 시도한다."""
    for attempt in range(attempts):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05)


def _clips_dir(app: FastAPI) -> Path:
    return resolve_paths(app.state.config.paths).clips


def _source_root(app: FastAPI, source: str) -> Path:
    resolved = resolve_paths(app.state.config.paths)
    if source == "steam":
        return resolved.clips
    if source == "vod":
        return resolved.vod_clips
    raise HTTPException(400, "source 는 steam 또는 vod 여야 합니다")


def _locate(app: FastAPI, clip_id: str):
    """클립 ID 로 스팀·다시보기 폴더(와 각 휴지통)를 모두 찾는다. ID 가 겹치지 않으므로(다시보기는 vod_ 로 시작) 나머지 라우트는 그대로 쓴다.

    (그 클립이 있는 폴더, 클립, 휴지통에 있는지) 를 돌려준다.
    """
    resolved = resolve_paths(app.state.config.paths)
    for root in (resolved.clips, resolved.vod_clips):
        clip = find_clip(root, clip_id)
        if clip is not None:
            return root, clip, False
        clip = find_clip(root / ".trash", clip_id)
        if clip is not None:
            return root, clip, True
    return None


def create_app(cfg: Config, *, config_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="Lumia Briefing Room API")
    app.state.config = cfg
    app.state.config_path = config_path
    app.state.log_dir = None
    lock = threading.RLock()
    jobs: dict[str, dict] = {}

    def locked(fn):
        """클립 파일을 읽거나 옮기거나 지우는 요청은 한 번에 하나씩 처리한다. 동시에 지우는 요청끼리 부딪혀 500 이 나던 문제를 막는다."""

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with lock:
                return fn(*args, **kwargs)

        return wrapper

    @app.get("/api/clips")
    @locked
    def list_clips(
        tags: str = "",
        dayNight: str | None = None,
        gameMode: str | None = None,
        pinned: bool = False,
        trashed: bool = False,
        minPvpScore: float | None = None,
        label: str | None = None,
        sort: str | None = None,
        source: str = "steam",
    ):
        clips_dir = _source_root(app, source)
        target = (clips_dir / ".trash") if trashed else clips_dir
        summaries = scan_clips(target)
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
        found = _locate(app, clip_id)
        if found is None:
            raise HTTPException(404, "클립을 찾을 수 없습니다")
        return _serialize(found[1])

    @app.patch("/api/clips/{clip_id}")
    @locked
    def patch_clip(clip_id: str, body: dict):
        found = _locate(app, clip_id)
        if found is None or found[2]:
            raise HTTPException(404, "클립을 찾을 수 없습니다")
        clip = found[1]
        if "userLabel" in body and body["userLabel"] not in (None, "pvp", "pve"):
            raise HTTPException(400, "라벨은 교전(pvp), 사냥(pve), 해제(null)만 지정할 수 있습니다")
        meta = {**clip.meta, **{k: v for k, v in body.items() if k in ("title", "pinned", "userLabel")}}
        if "userLabel" in body:
            meta["labelSource"] = "user" if body["userLabel"] is not None else None
            meta["labelConflict"] = False
        clip.meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta | {"id": clip_id}

    @app.post("/api/clips/{clip_id}/trash")
    @locked
    def trash(clip_id: str):
        found = _locate(app, clip_id)
        if found is None or found[2]:
            raise HTTPException(404, "클립을 찾을 수 없습니다")
        root, clip, _ = found
        trash_clip(clip.meta_path, root / ".trash")
        return {"id": clip_id, "trashed": True}

    @app.post("/api/clips/{clip_id}/restore")
    @locked
    def restore(clip_id: str):
        found = _locate(app, clip_id)
        if found is None or not found[2]:
            raise HTTPException(404, "휴지통에 없는 클립입니다")
        clips_dir, clip, _ = found
        restore_clip(clip.meta_path, clips_dir)
        return {"id": clip_id, "trashed": False}

    @app.delete("/api/clips/{clip_id}")
    @locked
    def delete(clip_id: str):
        found = _locate(app, clip_id)
        if found is None or not found[2]:
            raise HTTPException(400, "휴지통에 있는 클립만 완전히 삭제할 수 있습니다")
        clips_dir, clip, _ = found
        archive_if_labeled(clip.meta_path, archive_dir_for(clips_dir))
        record_game(clip.meta_path, records_dir_if_kept(clips_dir))
        for f in [clip.meta_path.with_suffix(".mp4"), clip.meta_path]:
            _unlink(f)
        thumb = clip.meta.get("thumbnailPath")
        if thumb:
            _unlink(Path(thumb))
        remove_orphan_result_images(clips_dir, clips_dir / ".trash")
        return {"id": clip_id, "deleted": True}

    def records_dir_if_kept(clips_dir: Path) -> Path | None:
        if clips_dir != _clips_dir(app) or not current_config().retention.keep_game_records:
            return None
        return records_dir_for(clips_dir)

    @app.get("/api/games/records")
    @locked
    def list_game_records():
        """클립이 다 지워진 경기의 기록. 살아있는 클립이 있는 경기는 그 클립이 게임 행을 그리므로 뺀다."""
        clips_dir = _clips_dir(app)
        live = {game_key(c.meta.get("sessionDir"), c.meta.get("matchStartUtc")) for c in scan_clips(clips_dir)}
        return [r for r in load_records(records_dir_for(clips_dir)) if r["id"] not in live]

    def _record_image(record_id: str) -> Path:
        if not re.fullmatch(r"[0-9A-Za-z._-]+", record_id) or record_id.startswith("."):
            raise HTTPException(404, "게임 기록을 찾을 수 없습니다")
        path = records_dir_for(_clips_dir(app)) / f"{record_id}.jpg"
        if not path.exists():
            raise HTTPException(404, "결과 화면 이미지가 없습니다")
        return path

    @app.get("/api/games/records/{record_id}/result-image")
    def game_record_image(record_id: str):
        return FileResponse(_record_image(record_id), media_type="image/jpeg")

    @app.delete("/api/games/records/{record_id}")
    @locked
    def delete_game_record(record_id: str):
        if not re.fullmatch(r"[0-9A-Za-z._-]+", record_id) or record_id.startswith("."):
            raise HTTPException(404, "게임 기록을 찾을 수 없습니다")
        if not delete_record(records_dir_for(_clips_dir(app)), record_id):
            raise HTTPException(404, "게임 기록을 찾을 수 없습니다")
        return {"id": record_id, "deleted": True}

    def find_any(clip_id: str):
        found = _locate(app, clip_id)
        return found[1] if found else None

    @app.get("/api/clips/{clip_id}/video")
    def video(clip_id: str, request: Request):
        clip = find_any(clip_id)
        if clip is None:
            raise HTTPException(404, "클립을 찾을 수 없습니다")
        return _serve_range(clip.meta_path.with_suffix(".mp4"), request, media_type="video/mp4")

    @app.get("/api/clips/{clip_id}/thumbnail")
    def thumbnail(clip_id: str):
        clip = find_any(clip_id)
        if clip is None:
            raise HTTPException(404, "클립을 찾을 수 없습니다")
        thumb = clip.meta.get("thumbnailPath")
        if not thumb or not Path(thumb).exists():
            raise HTTPException(404, "썸네일이 없습니다")
        return FileResponse(thumb, media_type="image/jpeg")

    @app.get("/api/clips/{clip_id}/result-image")
    def result_image(clip_id: str):
        clip = find_any(clip_id)
        if clip is None:
            raise HTTPException(404, "클립을 찾을 수 없습니다")
        path = (clip.meta.get("matchResult") or {}).get("imagePath")
        if not path or not Path(path).exists():
            raise HTTPException(404, "결과 화면 이미지가 없습니다")
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/fs/dirs")
    def fs_dirs(path: str = ""):
        if not path:
            return {"path": "", "parent": None, "dirs": list_roots()}
        target = Path(path)
        if not target.is_dir():
            raise HTTPException(404, "폴더를 찾을 수 없습니다")
        try:
            dirs = list_subdirs(target)
        except OSError as e:
            raise HTTPException(403, f"폴더를 열 수 없습니다: {e}")
        return {"path": str(target), "parent": parent_of(target), "dirs": dirs}

    @app.post("/api/fs/mkdir")
    def fs_mkdir(body: dict):
        base = Path(str(body.get("path", "")))
        name = str(body.get("name", ""))
        if not is_valid_folder_name(name):
            raise HTTPException(400, "폴더 이름이 올바르지 않습니다")
        if not base.is_dir():
            raise HTTPException(404, "폴더를 찾을 수 없습니다")
        created = base / name
        created.mkdir(exist_ok=True)
        return {"path": str(created)}

    @app.post("/api/clips/{clip_id}/export")
    def export_clip(clip_id: str, body: dict):
        found = _locate(app, clip_id)
        if found is None or found[2]:
            raise HTTPException(404, "클립을 찾을 수 없습니다")
        clip = found[1]
        directory = Path(str(body.get("dir", "")))
        if not directory.is_dir():
            raise HTTPException(404, "저장할 폴더를 찾을 수 없습니다")
        stem = str(body.get("filename") or clip.meta.get("title") or clip_id)
        if stem.lower().endswith(".mp4"):
            stem = stem[:-4]
        saved = export_video(clip.meta_path.with_suffix(".mp4"), directory, stem)
        put_config({"paths": {"exportDefault": str(directory)}})
        return {"path": str(saved)}

    def current_config() -> Config:
        """설정 파일이 진실이다 — 워처가 닉네임을 학습해 파일에 쓰기 때문에 메모리 사본만 믿으면 그 값을 덮어쓴다."""
        path = app.state.config_path
        if path is not None and path.exists():
            app.state.config = load_config(path)
        return app.state.config

    @app.post("/api/clips/{clip_id}/trim")
    @locked
    def trim(clip_id: str, body: dict):
        found = _locate(app, clip_id)
        if found is None or found[2]:
            raise HTTPException(404, "클립을 찾을 수 없습니다")
        clip_root, clip, _ = found
        try:
            start, end = float(body["start"]), float(body["end"])
            validate_range(start, end, float(clip.meta.get("durationSec", 0.0)))
        except (KeyError, TypeError):
            raise HTTPException(400, "시작과 끝 시각을 숫자로 지정해야 합니다")
        except ValueError as e:
            raise HTTPException(400, str(e))
        ffmpeg = discover_ffmpeg()
        if ffmpeg is None:
            raise HTTPException(503, "ffmpeg를 찾을 수 없습니다")
        try:
            trim_clip(clip.meta_path, start, end, ffmpeg_path=ffmpeg, thumbnail=current_config().encode.thumbnail)
        except (OSError, subprocess.CalledProcessError) as e:
            raise HTTPException(500, f"자르기에 실패했습니다: {e}")
        return _serialize(find_clip(clip_root, clip_id))

    @app.post("/api/trash/empty")
    @locked
    def empty_trash(source: str = "steam"):
        clips_dir = _source_root(app, source)
        trash_dir = clips_dir / ".trash"
        deleted = freed = 0
        for clip in scan_clips(trash_dir):
            freed += clip.size_bytes
            archive_if_labeled(clip.meta_path, archive_dir_for(clips_dir))
            record_game(clip.meta_path, records_dir_if_kept(clips_dir))
            for f in [clip.meta_path.with_suffix(".mp4"), clip.meta_path]:
                _unlink(f)
            thumb = clip.meta.get("thumbnailPath")
            if thumb:
                _unlink(Path(thumb))
            deleted += 1
        remove_orphan_result_images(clips_dir, trash_dir)
        return {"deleted": deleted, "bytes": freed}

    @app.post("/api/games/reprocess", status_code=202)
    def start_reprocess(body: dict):
        clip_id = body.get("clipId")
        if not clip_id:
            raise HTTPException(400, "다시 분석할 게임의 클립을 지정해야 합니다")
        clip = find_clip(_clips_dir(app), clip_id)
        if clip is None:
            raise HTTPException(404, "클립을 찾을 수 없습니다")
        if any(j["state"] == "running" for j in jobs.values()):
            raise HTTPException(409, "다른 게임을 분석하는 중입니다. 끝난 뒤 다시 시도하세요")
        ffmpeg = discover_ffmpeg()
        if ffmpeg is None:
            raise HTTPException(503, "ffmpeg를 찾을 수 없습니다")
        cfg = current_config()
        recording_root = cfg.paths.steam_recording or discover_recording_root()
        if recording_root is None:
            raise HTTPException(503, "스팀 녹화 폴더를 찾을 수 없습니다")

        ref = GameRef(session_name=clip.meta["sessionDir"], match_start=clip.meta["matchStartUtc"])
        key = f"{ref.session_name}|{ref.match_start}"
        job = {"state": "running", "message": "", "clips": 0}
        jobs[key] = job
        clips_dir = _clips_dir(app)

        def run() -> None:
            try:
                written = reprocess_game(
                    clips_dir=clips_dir, trash_dir=clips_dir / ".trash", ref=ref, recording_root=recording_root,
                    boundaries=read_boundaries(cfg), cfg=cfg, ffmpeg_path=ffmpeg, guard=lock,
                )
                job.update(state="done", clips=len(written))
            except ReprocessError as e:
                job.update(state="error", message=str(e))
            except Exception as e:
                job.update(state="error", message=f"다시 분석에 실패했습니다: {e}")

        threading.Thread(target=run, daemon=True).start()
        return {"key": key}

    @app.get("/api/games/reprocess/{key:path}")
    def reprocess_status(key: str):
        if key not in jobs:
            raise HTTPException(404, "분석 작업을 찾을 수 없습니다")
        return jobs[key]

    @app.post("/api/cleanup")
    @locked
    def cleanup(body: dict):
        cfg = current_config()
        resolved = resolve_paths(cfg.paths)
        dry_run = bool(body.get("dryRun"))
        step = plan_cleanup if dry_run else run_cleanup
        plan = step(resolved.clips, resolved.trash, cfg.retention)
        return {
            "toTrash": len(plan.to_trash),
            "toPurge": len(plan.to_purge),
            "bytesToFree": plan.bytes_to_free,
            "applied": not dry_run and cfg.retention.auto_clean_enabled,
        }

    @app.get("/api/app-info")
    def get_app_info():
        return {"version": __version__, "mode": resolve_mode(current_config().app.mode, frozen=paths.is_frozen())}

    @app.get("/api/config")
    def get_config():
        return dataclass_to_camel_dict(current_config())

    @app.put("/api/config")
    def put_config(body: dict):
        current = dataclass_to_camel_dict(current_config())
        merged = _deep_merge(current, body)
        new_cfg = dataclass_from_camel_dict(Config, merged)
        app.state.config = new_cfg
        if app.state.config_path is not None:
            save_config(new_cfg, app.state.config_path)
        return dataclass_to_camel_dict(new_cfg)

    @app.post("/api/client-log", status_code=204)
    def post_client_log(body: ClientLog):
        """브라우저에서 난 오류를 서버 로그 파일에 [client] 접두로 남긴다(개발용, plan-ui.md §6)."""
        parts = [body.message, body.stack, body.url]
        text = " | ".join(p for p in parts if p)[:_CLIENT_LOG_LIMIT]
        client_log.warning("[client] %s %s", body.level, text)
        return Response(status_code=204)

    register_vod_routes(app, lock=lock, current_config=current_config, put_config=put_config)
    register_onboarding_routes(app, current_config=current_config, put_config=put_config)
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
