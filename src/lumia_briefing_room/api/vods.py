"""다시보기(VOD) API. (docs/plan-vod.md V4)

영상 목록은 설정의 vod.sources(파일 또는 폴더)를 훑어 만들고, 분석 작업은 한 번에 하나만 백그라운드 스레드로 돈다.
클립 자체(영상·썸네일·라벨·휴지통 등)는 기존 /api/clips 라우트가 클립 ID 로 처리한다(api/app.py).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException

from lumia_briefing_room.api.clips import scan_clips
from lumia_briefing_room.api.export import list_roots, list_subdirs, parent_of
from lumia_briefing_room.config import Config, discover_ffmpeg, resolve_paths
from lumia_briefing_room.pipeline.clip_assets import resolve_thumbnail
from lumia_briefing_room.pipeline.label_archive import archive_dir_for, archive_if_labeled
from lumia_briefing_room.pipeline.retention import restore_clip, trash_clip
from lumia_briefing_room.pipeline.vod_analyze import VodCancelled, VodProgress, analyze_vod
from lumia_briefing_room.pipeline.vod_store import load_index, vod_id
from lumia_briefing_room.video.vod import find_ffprobe, probe_video
from lumia_briefing_room.video_formats import VIDEO_EXTENSIONS



def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def discover_videos(sources: list[str], recursive: bool) -> list[Path]:
    """설정의 경로(파일 또는 폴더)에서 영상 파일을 찾는다. 없는 경로는 건너뛴다."""
    found: dict[Path, None] = {}
    for raw in sources:
        path = Path(raw)
        try:
            if path.is_file():
                if is_video(path):
                    found[path] = None
            elif path.is_dir():
                walker = path.rglob("*") if recursive else path.iterdir()
                for child in sorted(walker):
                    if child.is_file() and is_video(child):
                        found[child] = None
        except OSError:
            continue
    return list(found)


def _probe_duration(path: Path, ffmpeg: Path | None) -> float | None:
    ffprobe = find_ffprobe(ffmpeg) if ffmpeg else None
    if ffprobe is None:
        return None
    try:
        return probe_video(path, ffprobe_path=ffprobe).duration_sec
    except Exception:
        return None


def _known_index_ids(root: Path) -> list[str]:
    folder = root / ".vods"
    if not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.json") if not p.name.endswith(".states.jsonl.gz"))


def register_vod_routes(
    app: FastAPI,
    *,
    lock: threading.RLock,
    current_config: Callable[[], Config],
    put_config: Callable[[dict], dict],
) -> None:
    id_cache: dict[tuple[str, int, int], str] = {}
    duration_cache: dict[tuple[str, int, int], float | None] = {}
    job: dict = {}

    def root() -> Path:
        return resolve_paths(current_config().paths).vod_clips

    def file_id(path: Path) -> str | None:
        try:
            stat = path.stat()
            key = (str(path), stat.st_size, int(stat.st_mtime))
            if key not in id_cache:
                id_cache[key] = vod_id(path)
            return id_cache[key]
        except OSError:
            return None

    probe_lock = threading.Lock()
    pending: set[tuple[str, int, int]] = set()
    prober = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vod-probe")

    def probe_in_background(key: tuple[str, int, int], path: Path) -> None:
        try:
            value = _probe_duration(path, discover_ffmpeg())
        except Exception:
            value = None
        with probe_lock:
            duration_cache[key] = value
            pending.discard(key)

    def duration_of(path: Path) -> tuple[float | None, bool]:
        """(길이, 재는 중인지). 큰 영상은 길이를 재는 데 오래 걸려서(11GB 파일 실측 1분 이상) 목록 요청이 기다리지 않고 백그라운드로 잰다."""
        stat = path.stat()
        key = (str(path), stat.st_size, int(stat.st_mtime))
        with probe_lock:
            if key in duration_cache:
                return duration_cache[key], False
            if key not in pending:
                pending.add(key)
                prober.submit(probe_in_background, key, path)
            return None, True

    def clip_stats(directory: Path) -> dict[str, dict]:
        stats: dict[str, dict] = {}
        for clip in scan_clips(directory):
            vid = clip.meta.get("vodId")
            if vid:
                entry = stats.setdefault(vid, {"count": 0, "bytes": 0})
                entry["count"] += 1
                entry["bytes"] += clip.size_bytes
        return stats

    def running_for(vid: str) -> bool:
        return job.get("state") == "running" and job.get("id") == vid

    def status_of(vid: str, index: dict | None) -> str:
        if running_for(vid):
            return "analyzing"
        if index is None:
            return "new"
        status = index.get("status", "new")
        return "interrupted" if status == "analyzing" else status

    def entry_for(vid: str, path: Path, index: dict | None, active: dict, trashed: dict, cfg: Config) -> dict:
        exists = path.exists()
        size = path.stat().st_size if exists else (index or {}).get("size")
        duration = (index or {}).get("durationSec")
        probing = False
        if duration is None and exists:
            duration, probing = duration_of(path)
        return {
            "id": vid,
            "path": str(path),
            "name": path.name,
            "exists": exists,
            "sizeBytes": size,
            "durationSec": duration,
            "probing": probing,
            "width": (index or {}).get("width"),
            "height": (index or {}).get("height"),
            "status": status_of(vid, index),
            "analyzedSec": (index or {}).get("analyzedSec"),
            "error": (index or {}).get("error"),
            "streamer": cfg.vod.streamers.get(vid) or (index or {}).get("streamer"),
            "games": (index or {}).get("games", []),
            "clipCount": active.get(vid, {}).get("count", 0),
            "clipBytes": active.get(vid, {}).get("bytes", 0),
            "trashedCount": trashed.get(vid, {}).get("count", 0),
        }

    def collect() -> dict[str, tuple[Path, dict | None]]:
        cfg = current_config()
        base = root()
        found: dict[str, tuple[Path, dict | None]] = {}
        for path in discover_videos(cfg.vod.sources, cfg.vod.recursive):
            vid = file_id(path)
            if vid is not None:
                found[vid] = (path, load_index(base, vid))
        for vid in _known_index_ids(base):
            if vid not in found:
                index = load_index(base, vid)
                if index is not None:
                    found[vid] = (Path(index.get("path", vid)), index)
        return found

    @app.get("/api/vods")
    def list_vods():
        with lock:
            cfg = current_config()
            base = root()
            active, trashed = clip_stats(base), clip_stats(base / ".trash")
            return [
                entry_for(vid, path, index, active, trashed, cfg)
                for vid, (path, index) in sorted(collect().items(), key=lambda kv: kv[1][0].name.casefold())
            ]

    def require(vid: str) -> tuple[Path, dict | None]:
        found = collect().get(vid)
        if found is None:
            raise HTTPException(404, "다시보기 영상을 찾을 수 없습니다")
        return found

    @app.patch("/api/vods/{vid}")
    def patch_vod(vid: str, body: dict):
        require(vid)
        if "streamer" in body:
            name = str(body["streamer"] or "").strip()
            put_config({"vod": {"streamers": {vid: name}}})
        return {"id": vid, "streamer": current_config().vod.streamers.get(vid) or None}

    @app.post("/api/vods/{vid}/analyze", status_code=202)
    def start_analysis(vid: str, body: dict | None = None):
        body = body or {}
        path, _ = require(vid)
        if job.get("state") == "running":
            raise HTTPException(409, "다른 영상을 분석하는 중입니다. 끝난 뒤 다시 시도하세요")
        if not path.exists():
            raise HTTPException(404, "영상 파일이 없습니다. 파일을 옮겼다면 옵션에서 경로를 다시 지정하세요")
        ffmpeg = discover_ffmpeg()
        if ffmpeg is None:
            raise HTTPException(503, "ffmpeg를 찾을 수 없습니다")
        cfg = current_config()
        cancel = threading.Event()
        job.clear()
        job.update(
            id=vid, state="running", phase="decode", fraction=0.0, games=0, clips=0,
            message="시작하는 중", cancel=cancel,
        )
        force, rebuild = bool(body.get("force")), bool(body.get("rebuild"))

        def on_progress(p: VodProgress) -> None:
            job.update(phase=p.phase, fraction=p.fraction, games=p.games, clips=p.clips, message=p.message)

        def run() -> None:
            try:
                analyze_vod(
                    path, cfg, ffmpeg_path=ffmpeg, force=force, rebuild=rebuild,
                    on_progress=on_progress, cancel=cancel,
                )
                job.update(state="done", fraction=1.0, message="")
            except VodCancelled:
                job.update(state="cancelled", message="분석을 멈췄습니다. 다시 시작하면 이어서 합니다.")
            except Exception as exc:
                job.update(state="error", message=f"분석에 실패했습니다: {exc}")

        threading.Thread(target=run, daemon=True).start()
        return {"id": vid}

    def public_job() -> dict:
        return {k: v for k, v in job.items() if k != "cancel"}

    @app.get("/api/vods/{vid}/analyze")
    def analysis_status(vid: str):
        if job.get("id") == vid:
            return public_job()
        return {"id": vid, "state": "idle"}

    @app.post("/api/vods/{vid}/analyze/cancel")
    def cancel_analysis(vid: str):
        if not running_for(vid):
            raise HTTPException(409, "분석 중이 아닙니다")
        job["cancel"].set()
        job["message"] = "멈추는 중"
        return {"id": vid, "cancelling": True}

    def vod_clip_paths(directory: Path, vid: str) -> list:
        return [c for c in scan_clips(directory) if c.meta.get("vodId") == vid]

    @app.post("/api/vods/{vid}/trash")
    def trash_vod(vid: str):
        with lock:
            base = root()
            clips = vod_clip_paths(base, vid)
            for clip in clips:
                trash_clip(clip.meta_path, base / ".trash")
        return {"id": vid, "count": len(clips)}

    @app.post("/api/vods/{vid}/restore")
    def restore_vod(vid: str):
        with lock:
            base = root()
            clips = vod_clip_paths(base / ".trash", vid)
            for clip in clips:
                restore_clip(clip.meta_path, base)
        return {"id": vid, "count": len(clips)}

    @app.delete("/api/vods/{vid}/clips")
    def delete_vod_clips(vid: str):
        with lock:
            base = root()
            clips = vod_clip_paths(base / ".trash", vid)
            for clip in clips:
                archive_if_labeled(clip.meta_path, archive_dir_for(base))
                for f in (clip.meta_path.with_suffix(".mp4"), clip.meta_path):
                    f.unlink(missing_ok=True)
                thumb = resolve_thumbnail(clip.meta_path, clip.meta)
                if thumb is not None:
                    thumb.unlink(missing_ok=True)
        return {"id": vid, "count": len(clips)}

    @app.get("/api/fs/videos")
    def fs_videos(path: str = ""):
        if not path:
            return {"path": "", "parent": None, "dirs": list_roots(), "files": []}
        target = Path(path)
        if not target.is_dir():
            raise HTTPException(404, "폴더를 찾을 수 없습니다")
        try:
            dirs = list_subdirs(target)
            files = [
                {"name": f.name, "sizeBytes": f.stat().st_size}
                for f in sorted(target.iterdir(), key=lambda p: p.name.casefold())
                if f.is_file() and is_video(f)
            ]
        except OSError as exc:
            raise HTTPException(403, f"폴더를 열 수 없습니다: {exc}")
        return {"path": str(target), "parent": parent_of(target), "dirs": dirs, "files": files}
