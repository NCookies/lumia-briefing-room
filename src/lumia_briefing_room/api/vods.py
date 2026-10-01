"""다시보기(VOD) API. (docs/plan-vod.md V4)

영상 목록은 설정의 vod.sources(파일 또는 폴더)를 훑어 만들고, 분석 작업은 분석 대기열(`analysis_queue.py`)에서 한 번에 하나씩 돈다.
클립 자체(영상·썸네일·라벨·휴지통 등)는 기존 /api/clips 라우트가 클립 ID 로 처리한다(api/app.py).
"""

from __future__ import annotations

import itertools
import threading
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from lumia_briefing_room.api.analysis_queue import AlreadyRunning, AnalysisQueue
from lumia_briefing_room.api.clips import scan_clips
from lumia_briefing_room.api.export import list_roots, list_subdirs, parent_of
from lumia_briefing_room.config import Config, discover_ffmpeg, resolve_paths
from lumia_briefing_room.pipeline.delete_helper import delete_clip
from lumia_briefing_room.pipeline.ffmpeg_errors import describe_clip_error
from lumia_briefing_room.pipeline.label_archive import archive_dir_for
from lumia_briefing_room.pipeline.cleanup_registry import registry as cleanup_preview_registry
from lumia_briefing_room.pipeline.vod_analyze import VodCancelled, VodProgress, analyze_vod
from lumia_briefing_room.pipeline.game_files import GameNotFound, has_full_video, load_game
from lumia_briefing_room.pipeline.reanalyze_game import ReanalyzeError
from lumia_briefing_room.pipeline.vod_full_games import delete_vod_games
from lumia_briefing_room.pipeline.vod_upgrade import UpgradeError, can_upgrade, upgrade_vod_games
from lumia_briefing_room.pipeline.vod_dates import is_valid_iso_date, resolve_video_date
from lumia_briefing_room.pipeline.vod_store import cache_path, index_path, load_index, save_index, vod_id
from lumia_briefing_room.video.vod import VideoInfo, find_ffprobe, probe_video
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


def _probe_info(path: Path, ffmpeg: Path | None) -> VideoInfo | None:
    ffprobe = find_ffprobe(ffmpeg) if ffmpeg else None
    if ffprobe is None:
        return None
    try:
        return probe_video(path, ffprobe_path=ffprobe)
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
    info_cache: dict[tuple[str, int, int], VideoInfo | None] = {}
    queue: AnalysisQueue = app.state.analysis_queue
    jobs: dict[str, dict] = {}
    seq = itertools.count(1)

    def root() -> Path:
        return resolve_paths(current_config().paths).library_vod

    def video_roots() -> tuple[Path, ...]:
        return resolve_paths(current_config().paths).clip_roots

    def games_root() -> Path:
        return resolve_paths(current_config().paths).games_vod

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
            value = _probe_info(path, discover_ffmpeg())
        except Exception:
            value = None
        with probe_lock:
            info_cache[key] = value
            pending.discard(key)

    def info_of(path: Path) -> tuple[VideoInfo | None, bool]:
        """(영상 정보, 재는 중인지). 큰 영상은 길이를 재는 데 오래 걸려서(11GB 파일 실측 1분 이상) 목록 요청이 기다리지 않고 백그라운드로 잰다."""
        stat = path.stat()
        key = (str(path), stat.st_size, int(stat.st_mtime))
        with probe_lock:
            if key in info_cache:
                return info_cache[key], False
            if key not in pending:
                pending.add(key)
                prober.submit(probe_in_background, key, path)
            return None, True

    def clip_stats(directory: Path) -> dict[str, dict]:
        stats: dict[str, dict] = {}
        for clip in scan_clips(directory, video_roots()):
            vid = clip.meta.get("vodId")
            if vid:
                entry = stats.setdefault(vid, {"count": 0, "bytes": 0})
                entry["count"] += 1
                entry["bytes"] += clip.size_bytes
        return stats

    def jobs_of(vid: str) -> list[dict]:
        return [j for j in jobs.values() if j["id"] == vid]

    def running_for(vid: str) -> bool:
        return any(j["state"] == "running" for j in jobs_of(vid))

    def queued_for(vid: str) -> list[dict]:
        return sorted((j for j in jobs_of(vid) if j["state"] == "queued"), key=lambda j: j["seq"])

    def position_of(job: dict) -> int | None:
        return queue.position(job["queueKey"]) if job["state"] == "queued" else None

    def job_of(vid: str) -> dict | None:
        """영상의 대표 작업: 실행 중 > 대기 중(먼저 요청한 것) > 가장 최근에 끝난 것."""
        mine = jobs_of(vid)
        running = [j for j in mine if j["state"] == "running"]
        if running:
            return running[0]
        queued = queued_for(vid)
        if queued:
            return queued[0]
        return max(mine, key=lambda j: j["seq"]) if mine else None

    def status_of(vid: str, index: dict | None) -> str:
        if running_for(vid):
            return "analyzing"
        if any(j["kind"] == "analyze" for j in queued_for(vid)):
            return "queued"
        if index is None:
            return "new"
        status = index.get("status", "new")
        return "interrupted" if status == "analyzing" else status

    def saved_full_video_keys(index: dict | None) -> list[str]:
        """저장한 풀영상이 남아 있는 게임 키(원본 영상이 없어도 이것으로 다시 분석할 수 있다)."""
        return [
            g["gameKey"] for g in (index or {}).get("games", [])
            if g.get("gameKey") and has_full_video(games_root(), g["gameKey"])
        ]

    def sync_index_clips(vid: str) -> None:
        """게임 기록(`game.json`)의 연결된 클립으로 색인의 게임별 `clipIds` 와 `clips` 를 다시 맞춘다."""
        base = root()
        index = load_index(base, vid)
        if index is None:
            return
        for game in index.get("games", []):
            try:
                data = load_game(games_root(), game["gameKey"])
            except (GameNotFound, KeyError):
                continue
            rows = [*(data.get("candidates") or []), *(data.get("userCandidates") or [])]
            game["clipIds"] = sorted({(c.get("user") or {}).get("savedClipId") for c in rows} - {None})
        index["clips"] = sorted({cid for g in index.get("games", []) for cid in g.get("clipIds", [])})
        save_index(base, index)

    def entry_for(vid: str, path: Path, index: dict | None, active: dict, cfg: Config) -> dict:
        exists = path.exists()
        stat = path.stat() if exists else None
        size = stat.st_size if stat else (index or {}).get("size")
        duration = (index or {}).get("durationSec")
        creation_time = (index or {}).get("creationTime")
        probing = False
        if duration is None and exists:
            info, probing = info_of(path)
            if info is not None:
                duration, creation_time = info.duration_sec, info.creation_time
        video_date = resolve_video_date(
            override=cfg.vod.video_dates.get(vid),
            creation_time=creation_time,
            mtime=stat.st_mtime if stat else None,
        )
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
            "queuePosition": next((position_of(j) for j in queued_for(vid) if j["kind"] == "analyze"), None),
            "analyzedSec": (index or {}).get("analyzedSec"),
            "error": (index or {}).get("error"),
            "errorKind": (index or {}).get("errorKind"),
            "sourceDeleted": (index or {}).get("sourceDeleted", False),
            "canBuildFullVideos": exists and can_upgrade(index, path, root()),
            "canReanalyzeFromFullVideos": not exists and bool(saved_full_video_keys(index)),
            "streamer": cfg.vod.streamers.get(vid) or (index or {}).get("streamer"),
            "videoDate": video_date,
            "games": (index or {}).get("games", []),
            "clipCount": active.get(vid, {}).get("count", 0),
            "clipBytes": active.get(vid, {}).get("bytes", 0),
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
            active = clip_stats(base)
            return [
                entry_for(vid, path, index, active, cfg)
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
        if "date" in body:
            date = str(body["date"] or "").strip()
            if date and not is_valid_iso_date(date):
                raise HTTPException(400, "날짜는 YYYY-MM-DD 형식이어야 합니다")
            put_config({"vod": {"videoDates": {vid: date}}})
        return {
            "id": vid,
            "streamer": current_config().vod.streamers.get(vid) or None,
            "date": current_config().vod.video_dates.get(vid) or None,
        }

    def submit(vid: str, kind: str, name: str, label: str, initial: dict, run) -> dict:
        """같은 대상(`name`)이 이미 대기 중이면 그 요청을 최신 것으로 바꾸고, 실행 중이면 줄 세우지 않고 그대로 둔다."""
        queue_key = f"vod:{name}"
        job = jobs.get(name)
        if job is None or job["state"] not in ("queued", "running"):
            job = {
                "id": vid, "kind": kind, "state": "queued", "phase": "decode", "fraction": 0.0, "games": 0, "clips": 0,
                "message": "", "cancel": threading.Event(), "seq": next(seq), "queueKey": queue_key, **initial,
            }
            jobs[name] = job

        def go() -> None:
            if job["state"] != "queued":
                return
            job.update(state="running", message="시작하는 중")
            run(job)

        try:
            queue.submit(queue_key, label, go)
        except AlreadyRunning:
            pass
        return job

    @app.post("/api/vods/{vid}/analyze", status_code=202)
    def start_analysis(vid: str, body: dict | None = None):
        body = body or {}
        path, index = require(vid)
        from_full = not path.exists() and bool(saved_full_video_keys(index))
        if not path.exists() and not from_full:
            raise HTTPException(404, "영상 파일이 없습니다. 파일을 옮겼다면 옵션에서 경로를 다시 지정하세요")
        ffmpeg = discover_ffmpeg()
        if ffmpeg is None:
            raise HTTPException(503, "ffmpeg를 찾을 수 없습니다")
        if from_full:
            reanalyze_from_full_videos(vid, path, ffmpeg)
            return {"id": vid}
        cfg = current_config()
        force, rebuild = bool(body.get("force")), bool(body.get("rebuild"))
        delete_source = body.get("deleteSource")
        if delete_source is not None and not isinstance(delete_source, bool):
            raise HTTPException(400, "deleteSource 는 true/false 여야 합니다")

        def run(job: dict) -> None:
            def on_progress(p: VodProgress) -> None:
                job.update(phase=p.phase, fraction=p.fraction, games=p.games, clips=p.clips, message=p.message)

            try:
                analyze_vod(
                    path, cfg, ffmpeg_path=ffmpeg, force=force, rebuild=rebuild,
                    on_progress=on_progress, cancel=job["cancel"], delete_source=delete_source,
                )
                job.update(state="done", fraction=1.0, message="")
            except VodCancelled:
                job.update(state="cancelled", message="분석을 멈췄습니다. 다시 시작하면 이어서 합니다.")
            except Exception as exc:
                job.update(state="error", message=describe_clip_error(exc))

        submit(vid, "analyze", f"analyze:{vid}", f"영상 분석 ({path.name})", {}, run)
        return {"id": vid}

    def reanalyze_from_full_videos(vid: str, path: Path, ffmpeg: Path) -> None:
        """원본 영상이 없을 때: 저장한 게임 풀영상마다 후보·결과·초상화를 다시 찾고 자동 저장 클립을 다시 뽑는다(보관한 클립은 그대로)."""
        keys = saved_full_video_keys(load_index(root(), vid))

        def run(job: dict) -> None:
            reanalyze = app.state.game_reanalyze.run
            made = failed = 0
            try:
                for i, key in enumerate(keys):
                    if job["cancel"].is_set():
                        raise VodCancelled()
                    job.update(message=f"게임 {i + 1}/{len(keys)} 풀영상에서 클립 다시 추출", games=i + 1)
                    _, m, f = reanalyze(
                        key, ffmpeg, cancel=job["cancel"],
                        on_progress=lambda fr, i=i: job.update(fraction=(i + fr) / len(keys)),
                    )
                    made, failed = made + m, failed + f
                sync_index_clips(vid)
                job.update(state="done", fraction=1.0, message="", clipsMade=made, clipsFailed=failed)
            except VodCancelled:
                sync_index_clips(vid)
                job.update(state="cancelled", message="멈췄습니다. 다시 누르면 처음부터 다시 추출합니다.")
            except ReanalyzeError as exc:
                sync_index_clips(vid)
                cancelled = job["cancel"].is_set()
                job.update(state="cancelled" if cancelled else "error", message="멈췄습니다." if cancelled else str(exc))
            except Exception as exc:
                job.update(state="error", message=describe_clip_error(exc))
            finally:
                cleanup_preview_registry.notify_clips_changed()

        submit(vid, "analyze", f"analyze:{vid}", f"풀영상에서 클립 다시 추출 ({path.name})", {"fromFullVideos": True, "games": len(keys)}, run)

    def start_full_videos(vid: str, only: set[int] | None = None) -> None:
        """이미 분석한 영상의 게임을 풀영상으로 만든다(분석 작업과 같은 대기열: 한 번에 하나, 진행률·취소 공용)."""
        path, index = require(vid)
        if not path.exists() or not can_upgrade(index, path, root()):
            raise HTTPException(409, "원본 영상이나 이전 분석 기록이 없어 풀영상을 만들 수 없습니다")
        ffmpeg = discover_ffmpeg()
        if ffmpeg is None:
            raise HTTPException(503, "ffmpeg를 찾을 수 없습니다")
        cfg = current_config()
        base, gdir = root(), games_root()

        def run(job: dict) -> None:
            try:
                upgrade_vod_games(
                    path, cfg, ffmpeg_path=ffmpeg, root=base, games_dir=gdir, index=load_index(base, vid), only=only,
                    cancel=job["cancel"], on_progress=lambda f, m: job.update(fraction=f, message=m),
                )
                job.update(state="done", fraction=1.0, message="")
                cleanup_preview_registry.notify_clips_changed()
            except VodCancelled:
                job.update(state="cancelled", message="멈췄습니다. 다시 누르면 남은 게임부터 만듭니다.")
            except UpgradeError as exc:
                job.update(state="error", message=str(exc))
            except Exception as exc:
                job.update(state="error", message=describe_clip_error(exc))

        name = f"full:{vid}:{','.join(str(i) for i in sorted(only)) if only else 'all'}"
        submit(
            vid, "fullVideos", name, f"풀영상 만들기 ({path.name})",
            {"phase": "full", "games": len(index["games"]), "only": sorted(only) if only else None}, run,
        )

    def full_video_status(vid: str, index: int) -> dict:
        """게임 화면의 "풀영상 만들기" 버튼이 읽는 모양(스팀 쪽과 같다): state/message/fraction(+대기 중이면 position)."""
        mine = [j for j in jobs_of(vid) if j["kind"] == "fullVideos" and (not j.get("only") or index in j["only"])]
        if not mine:
            return {"state": "idle", "message": "", "fraction": 0.0}
        job = max(mine, key=lambda j: ({"running": 2, "queued": 1}.get(j["state"], 0), j["seq"]))
        state = job["state"]
        return {
            "state": "error" if state in ("error", "cancelled") else state,
            "message": "" if state == "queued" else job["message"], "fraction": job["fraction"], "position": position_of(job),
        }

    def can_build(vid: str) -> bool:
        found = collect().get(vid)
        return found is not None and found[0].exists() and can_upgrade(found[1], found[0], root())

    app.state.vod_full_videos = SimpleNamespace(start=start_full_videos, status=full_video_status, can_build=can_build)

    @app.post("/api/vods/{vid}/full-videos", status_code=202)
    def build_full_videos(vid: str):
        start_full_videos(vid)
        return {"id": vid}

    def public_job(job: dict) -> dict:
        return {**{k: v for k, v in job.items() if k not in ("cancel", "seq", "queueKey")}, "position": position_of(job)}

    @app.get("/api/vods/{vid}/analyze")
    def analysis_status(vid: str):
        job = job_of(vid)
        return public_job(job) if job is not None else {"id": vid, "state": "idle"}

    @app.post("/api/vods/{vid}/analyze/cancel")
    def cancel_analysis(vid: str):
        """실행 중이면 멈추고, 대기 중이면 줄에서 뺀다(대기 중인 것이 여럿이면 모두)."""
        running = next((j for j in jobs_of(vid) if j["state"] == "running"), None)
        if running is not None:
            running["cancel"].set()
            running["message"] = "멈추는 중"
            return {"id": vid, "cancelling": True}
        waiting = queued_for(vid)
        if not waiting:
            raise HTTPException(409, "분석 중이 아닙니다")
        for job in waiting:
            if queue.cancel(job["queueKey"]):
                job.update(state="cancelled", message="대기를 취소했습니다")
        return {"id": vid, "cancelling": False, "cancelledQueued": len(waiting)}

    def vod_clip_paths(directory: Path, vid: str) -> list:
        return [c for c in scan_clips(directory, video_roots()) if c.meta.get("vodId") == vid]

    @app.delete("/api/vods/{vid}/clips")
    def delete_vod_clips(vid: str):
        """"전체 삭제" - 클립을 지우고 분석 결과(게임 목록)도 지워 "분석 안 함" 상태로
        되돌린다. 클립만 지우면 클립 0개짜리 게임 요약 행이 목록에 계속 남아 "완전히
        지웠다가 다시 만들고 싶은데 목록에서 안 없어진다"는 실사용 보고가 있었다
        (2026-09-27) - 클립 없는 게임 요약은 그 자체로 남겨 둘 이유가 없다."""
        with lock:
            base = root()
            clips = vod_clip_paths(base, vid)
            archive_dir = archive_dir_for(base)
            mode = current_config().ui.delete_mode
            for clip in clips:
                delete_clip(clip.meta_path, mode=mode, archive_dir=archive_dir, video=clip.video)
            delete_vod_games(games_root(), vid, mode=mode)
            index = load_index(base, vid)
            if index is not None:
                # decodeDone/analyzedSec 은 그대로 둔다 - 프레임 판독 캐시는 영상 자체가
                # 안 바뀌면 그대로 유효하므로, 다음 "분석 시작"이 처음부터 다시 디코드하지
                # 않고 캐시를 그대로 써서 게임·클립만 빠르게 다시 만들게 한다.
                index.update(games=[], clips=[], status="new", error=None, errorKind=None)
                save_index(base, index)
        return {"id": vid, "count": len(clips)}

    @app.delete("/api/vods/{vid}")
    def delete_vod(vid: str):
        """다시보기를 목록에서 완전히 지운다 - 클립·판독 캐시·색인을 모두 지운다.

        원본 영상 파일은 건드리지 않는다 - 아직 있으면 다음 목록 조회 때 "분석 안 함"으로
        다시 나타난다(`collect()` 가 `cfg.vod.sources` 를 다시 훑으므로). 원본까지 이미
        지워졌다면(예: "성공 시 원본 삭제" 설정, `sourceDeleted`) 목록에서도 완전히
        사라진다 - "원본도 클립도 다 지웠는데 게임 항목이 목록에 남아 지울 방법이 없다"는
        실사용 보고(2026-09-29)에 대응한다. `delete_vod_clips`(전체 삭제)는 색인은 남기고
        게임·클립만 비워 "분석 안 함"으로 되돌리는 것과 달리, 이건 색인 자체를 지운다.
        """
        require(vid)
        if running_for(vid) or queued_for(vid):
            raise HTTPException(409, "분석 중이거나 분석을 기다리는 영상은 지울 수 없습니다. 먼저 분석을 취소하세요")
        with lock:
            base = root()
            clips = vod_clip_paths(base, vid)
            archive_dir = archive_dir_for(base)
            mode = current_config().ui.delete_mode
            for clip in clips:
                delete_clip(clip.meta_path, mode=mode, archive_dir=archive_dir, video=clip.video)
            delete_vod_games(games_root(), vid, mode=mode)
            index_path(base, vid).unlink(missing_ok=True)
            cache_path(base, vid).unlink(missing_ok=True)
        return {"id": vid, "deletedClips": len(clips)}

    @app.delete("/api/vods/{vid}/games/{game_index}")
    def delete_vod_game(vid: str, game_index: int):
        """게임 하나만 지운다 - 클립을 지우고 게임 요약도 목록에서 없앤다(스팀 쪽 "게임
        삭제"가 기록도 같이 지우는 것과 같은 원칙). 클립이 0개인 게임(교전을 못 뽑았지만
        결과 화면은 읽은 경우, plan.md §10-6)도 이걸로 지워야 목록에서 사라진다 -
        클립이 없어 기존 클립 삭제 경로가 아무것도 안 했다."""
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
            archive_dir = archive_dir_for(base)
            mode = current_config().ui.delete_mode
            for clip in clips:
                delete_clip(clip.meta_path, mode=mode, archive_dir=archive_dir, video=clip.video)
            delete_vod_games(games_root(), vid, mode=mode, only_index=game_index)
            index["games"] = [g for g in games if g.get("index") != game_index]
            index["clips"] = [c for c in index.get("clips", []) if c not in clip_ids]
            save_index(base, index)
        return {"id": vid, "index": game_index, "deletedClips": len(clips)}

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
