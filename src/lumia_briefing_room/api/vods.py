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
from fastapi.responses import FileResponse

from lumia_briefing_room.api.clips import scan_clips
from lumia_briefing_room.api.export import list_roots, list_subdirs, parent_of
from lumia_briefing_room.config import Config, discover_ffmpeg, resolve_paths
from lumia_briefing_room.pipeline.clip_assets import resolve_thumbnail
from lumia_briefing_room.pipeline.label_archive import archive_dir_for, archive_if_labeled
from lumia_briefing_room.pipeline.retention import restore_clip, trash_clip
from lumia_briefing_room.pipeline.vod_analyze import VodCancelled, VodProgress, analyze_vod
from lumia_briefing_room.pipeline.vod_store import load_index, save_index, vod_id
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

    @app.get("/api/vods/{vid}/games/{game_index}/result-image")
    def vod_game_result_image(vid: str, game_index: int):
        """클립이 없는 게임(교전을 못 뽑았지만 결과 화면은 읽은 경우, plan.md §10-6)도
        결과표 이미지를 보여준다 - 클립 ID 로 찾는 `/api/clips/{id}/result-image` 를 못 쓴다."""
        _, index = require(vid)
        game = next((g for g in (index or {}).get("games", []) if g.get("index") == game_index), None)
        image_path = ((game or {}).get("result") or {}).get("imagePath")
        if not image_path:
            raise HTTPException(404, "결과 화면 이미지가 없습니다")
        base = root().resolve()
        full = (base / image_path).resolve()
        if base not in full.parents or not full.exists():
            raise HTTPException(404, "결과 화면 이미지가 없습니다")
        return FileResponse(full, media_type="image/jpeg")

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
        """"전체 삭제" - 클립을 휴지통으로 옮기고 분석 결과(게임 목록)도 지워 "분석 안 함"
        상태로 되돌린다. 클립만 지우면 클립 0개짜리 게임 요약 행이 목록에 계속 남아
        "완전히 지웠다가 다시 만들고 싶은데 목록에서 안 없어진다"는 실사용 보고가 있었다
        (2026-09-27) - 클립 없는 게임 요약은 그 자체로 남겨 둘 이유가 없다."""
        with lock:
            base = root()
            clips = vod_clip_paths(base, vid)
            for clip in clips:
                trash_clip(clip.meta_path, base / ".trash")
            index = load_index(base, vid)
            if index is not None:
                # decodeDone/analyzedSec 은 그대로 둔다 - 프레임 판독 캐시는 영상 자체가
                # 안 바뀌면 그대로 유효하므로, 다음 "분석 시작"이 처음부터 다시 디코드하지
                # 않고 캐시를 그대로 써서 게임·클립만 빠르게 다시 만들게 한다.
                index.update(games=[], clips=[], status="new", error=None)
                save_index(base, index)
        return {"id": vid, "count": len(clips)}

    @app.delete("/api/vods/{vid}/games/{game_index}")
    def delete_vod_game(vid: str, game_index: int):
        """게임 하나만 지운다 - 클립을 휴지통으로 옮기고 게임 요약도 목록에서 없앤다
        (스팀 쪽 "게임 삭제"가 기록도 같이 지우는 것과 같은 원칙). 클립이 0개인 게임
        (교전을 못 뽑았지만 결과 화면은 읽은 경우, plan.md §10-6)도 이걸로 지워야
        목록에서 사라진다 - 클립이 없어 기존 클립 삭제 경로가 아무것도 안 했다."""
        with lock:
            base = root()
            index = load_index(base, vid)
            if index is None:
                raise HTTPException(404, "분석 기록이 없습니다")
            games = index.get("games", [])
            game = next((g for g in games if g.get("index") == game_index), None)
            if game is None:
                raise HTTPException(404, "그런 게임이 없습니다")
            clip_ids = set(game.get("clipIds", []))
            clips = [c for c in vod_clip_paths(base, vid) if c.id in clip_ids]
            for clip in clips:
                trash_clip(clip.meta_path, base / ".trash")
            index["games"] = [g for g in games if g.get("index") != game_index]
            index["clips"] = [c for c in index.get("clips", []) if c not in clip_ids]
            save_index(base, index)
        return {"id": vid, "index": game_index, "trashedClips": len(clips)}

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
