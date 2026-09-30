"""게임(풀영상) API. (plan-fullvideo.md §3.6, F4)

기존 클립 API 는 그대로 두고 새 경로만 추가한다(UI 를 되돌릴 수 있게, plan §5). 사용자 수정은 `game.json` 의
`candidates[].user` 에만 쓰고 자동 검출 값은 건드리지 않는다.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from lumia_briefing_room import activity
from lumia_briefing_room.api.clips import find_clip
from lumia_briefing_room.pipeline import categories as cats
from lumia_briefing_room.pipeline.library_fs import LibraryError
from lumia_briefing_room.config import AUTO_ARCHIVE_FOLDER, Config, discover_ffmpeg, resolve_paths
from lumia_briefing_room.pipeline import game_candidates as gcand
from lumia_briefing_room.pipeline.clip_from_full import FullVideoMissing
from lumia_briefing_room.pipeline.game_clip_save import save_and_mark
from lumia_briefing_room.pipeline.cleanup_registry import registry as cleanup_preview_registry
from lumia_briefing_room.pipeline.cleanup import remove_orphan_result_images
from lumia_briefing_room.pipeline.delete_helper import PERMANENT, delete_clip, send_to_recycle_bin
from lumia_briefing_room.pipeline.ffmpeg_errors import describe_clip_error
from lumia_briefing_room.pipeline.game_cleanup import delete_full_video
from lumia_briefing_room.pipeline.game_records import delete_record, game_key, records_dir_for
from lumia_briefing_room.pipeline.label_archive import archive_dir_for
from lumia_briefing_room.pipeline.proxy import proxy_file
from lumia_briefing_room.pipeline.game_files import GameNotFound, game_dir, has_full_video, list_games, load_game, update_game
from lumia_briefing_room.pipeline.game_store import FULL_VIDEO
from lumia_briefing_room.pipeline.legacy_games import migrate_legacy_games
from lumia_briefing_room.pipeline.legacy_vod_games import migrate_legacy_vod_games
from lumia_briefing_room.pipeline.rebuild_full_video import RebuildError, can_rebuild, rebuild_full_video
from lumia_briefing_room.pipeline.reanalyze_game import ReanalyzeError, reanalyze_game, reanalyze_mode
from lumia_briefing_room.steam_paths import resolve_recording_root

log = logging.getLogger(__name__)

_ASSETS = {"result.jpg", "portrait_me.jpg", "portrait_teammate1.jpg", "portrait_teammate2.jpg"}


class GamePatch(BaseModel):
    pinned: bool | None = None


class CandidateCreate(BaseModel):
    start: float
    end: float
    title: str | None = None


class GameDelete(BaseModel):
    target: str  # fullVideo | clips | both


class SaveOptions(BaseModel):
    category: str | None = None


class BatchSave(BaseModel):
    mode: str = "all"  # all | certain | ids
    ids: list[str] | None = None
    category: str | None = None


def _summary(game: dict, games_dir: Path, *, can_rebuild_full: bool = False) -> dict:
    cands = gcand.all_candidates(game)
    active = [c for c in cands if not (c.get("user") or {}).get("dismissed")]
    video = game.get("fullVideo") or {}
    return {
        "key": game["gameKey"],
        "source": game.get("source") or "steam",
        "vodId": game.get("vodId"),
        "gameIndex": game.get("vodGameIndex"),
        "streamer": game.get("streamer"),
        "vodStartSec": game.get("vodStartSec"),
        "vodEndSec": game.get("vodEndSec"),
        "matchStartUtc": game.get("matchStartUtc"),
        "matchEndUtc": game.get("matchEndUtc"),
        "gameMode": game.get("gameMode"),
        "matchResult": game.get("matchResult"),
        "portraits": game.get("portraits") or {},
        "pinned": bool(game.get("pinned")),
        "sourceIncomplete": bool(game.get("sourceIncomplete")),
        "hasFullVideo": has_full_video(games_dir, game["gameKey"]),
        "fullVideoSizeBytes": video.get("sizeBytes"),
        "durationSec": video.get("durationSec"),
        "fullVideoError": game.get("fullVideoError"),
        "legacy": bool(game.get("legacy")),
        "canRebuildFullVideo": can_rebuild_full,
        "fullVideoDeletedAt": game.get("fullVideoDeletedAt"),
        "candidateCount": len(active),
        "certainCount": sum(1 for c in active if c.get("certain")),
        "savedClipCount": sum(1 for c in cands if (c.get("user") or {}).get("savedClipId")),
        "unsavedEditCount": sum(1 for c in active if (c.get("user") or {}).get("savedClipId") and gcand.range_changed(c, float(video.get("durationSec") or 0.0))),
    }


def register_game_routes(
    app: FastAPI, *, lock, current_config: Callable[[], Config]
) -> None:
    migrate_lock = threading.Lock()

    def games_dir(key: str) -> Path:
        """게임 키로 풀영상 폴더를 고른다(영상 파일 게임 키는 `vod_` 로 시작). 옛 경로 모드에선 둘이 같은 폴더다."""
        resolved = resolve_paths(current_config().paths)
        return resolved.games_vod if key.startswith("vod_") else resolved.games_steam

    def games_dirs(source: str) -> list[Path]:
        resolved = resolve_paths(current_config().paths)
        wanted = {"steam": [resolved.games_steam], "vod": [resolved.games_vod]}.get(source, [resolved.games_steam, resolved.games_vod])
        return list(dict.fromkeys(wanted))

    def clips_dir() -> Path:
        """클립 정보(library) 폴더."""
        return resolve_paths(current_config().paths).library_steam

    def vod_clips_dir() -> Path:
        return resolve_paths(current_config().paths).library_vod

    def clips_dir_for(game: dict) -> Path:
        """영상 파일 게임에서 저장한 클립은 스팀 클립과 섞이지 않게 영상 클립 정보 폴더에 둔다."""
        return vod_clips_dir() if game.get("source") == "vod" else clips_dir()

    migrated: set[tuple[Path, Path]] = set()
    migrated_vod: set[tuple[Path, Path]] = set()

    def migrate_vod_once() -> None:
        """영상 파일 탭이 처음 게임 목록을 볼 때 이전 버전에서 분석한 영상 게임을 게임 기록으로 옮긴다(스팀 쪽과 같은 이유)."""
        pair = (vod_clips_dir(), resolve_paths(current_config().paths).games_vod)
        with migrate_lock:
            if pair in migrated_vod:
                return
            migrated_vod.add(pair)
            try:
                migrate_legacy_vod_games(*pair)
            except Exception:
                log.exception("이전 버전 영상 게임 통합 실패")

    def migrate_once() -> None:
        """앱을 켠 뒤 처음 목록을 볼 때(경로를 바꾸면 그 경로에서 다시 한 번) 이전 버전 클립을 게임 기록으로 옮긴다.

        시작 시 자동보다 목록 요청 때가 안전하다: 경로를 옵션에서 바꾼 뒤에도 따라가고, 서버가 뜨는 동안 파일을 건드리지 않는다.
        """
        pair = (clips_dir(), resolve_paths(current_config().paths).games_steam)
        with migrate_lock:
            if pair in migrated:
                return
            migrated.add(pair)
            try:
                migrate_legacy_games(*pair)
            except Exception:
                log.exception("이전 버전 게임 통합 실패")

    def load_or_404(key: str) -> dict:
        try:
            return load_game(games_dir(key), key)
        except GameNotFound:
            raise HTTPException(404, "게임을 찾을 수 없습니다")

    def duration_of(game: dict) -> float:
        video = game.get("fullVideo") or {}
        return float(video.get("durationSec") or 0.0)

    @app.get("/api/games")
    def get_games(source: str = "steam"):
        """`source`: steam(기본) / vod(영상 파일 탭) / all. 두 탭의 게임은 같은 폴더에 있지만 목록은 따로 본다."""
        if source not in ("steam", "vod", "all"):
            raise HTTPException(400, "source 는 steam, vod, all 중 하나여야 합니다")
        if source in ("steam", "all"):
            migrate_once()
        if source in ("vod", "all"):
            migrate_vod_once()
        listed = [g for d in games_dirs(source) for g in list_games(d)]
        games = sorted(
            (g for g in listed if source == "all" or (g.get("source") or "steam") == source),
            key=lambda g: g.get("gameKey") or "", reverse=True,
        )
        recording_root = resolve_recording_root(current_config().paths.steam_recording)

        def rebuildable(g: dict) -> bool:
            """목록에서 "풀영상 만들기"를 보일 옛 스팀 게임만 원본이 남았는지 본다(영상 게임은 영상 묶음 머리 버튼)."""
            return (
                bool(g.get("legacy")) and (g.get("source") or "steam") == "steam"
                and can_rebuild(g, games_dir(g["gameKey"]), recording_root)
            )

        return {"games": [_summary(g, games_dir(g["gameKey"]), can_rebuild_full=rebuildable(g)) for g in games]}

    @app.get("/api/games/{key}")
    def get_game(key: str):
        game = load_or_404(key)
        if game.get("source") == "vod":
            can = (
                not game.get("fullVideoDeletedAt") and not has_full_video(games_dir(key), key)
                and vod_control().can_build(game["vodId"])
            )
        else:
            can = can_rebuild(game, games_dir(key), resolve_recording_root(current_config().paths.steam_recording))
        self_saved_category(game)
        return {**game, "hasFullVideo": has_full_video(games_dir(key), key), "canRebuildFullVideo": can}

    def category_of_clip(game: dict, clip_id: str) -> str | None:
        cfg = current_config()
        if not cats.enabled(cfg):
            return None
        clip = find_clip(clips_dir_for(game), clip_id, resolve_paths(cfg.paths).clip_roots)
        return cats.category_of(cfg, clip.video) if clip is not None else None

    def self_saved_category(game: dict) -> None:
        """클립이 있는 후보마다 지금 어느 카테고리에 있는지(`user.savedCategory`), **보관됨 여부(`user.archived`)**, 클립 메모(`user.savedMemo`)를 붙인다(저장하지 않는 계산 값).

        보관됨 = 자동 보관이 아닌 카테고리에 있는 클립. `자동 보관` 의 클립은 클립 파일은 있어도 어디에도 속하지 않은 것으로 본다(옛 경로 모드는 카테고리가 없어 클립이 있으면 보관됨)."""
        cfg = current_config()
        roots = resolve_paths(cfg.paths).clip_roots
        for cand in gcand.all_candidates(game):
            user = cand.get("user") or {}
            if not user.get("savedClipId"):
                continue
            clip = find_clip(clips_dir_for(game), user["savedClipId"], roots)
            if clip is None:
                continue
            extra: dict = {}
            name = cats.category_of(cfg, clip.video) if cats.enabled(cfg) else None
            if name:
                extra["savedCategory"] = name
            extra["archived"] = not cats.enabled(cfg) or (name is not None and name != AUTO_ARCHIVE_FOLDER)
            if isinstance(clip.meta.get("memo"), str) and clip.meta["memo"]:
                extra["savedMemo"] = clip.meta["memo"]
            if extra:
                cand["user"] = {**user, **extra}

    rebuild_jobs: dict[str, dict] = {}

    def vod_control():
        """영상 분석 작업을 관리하는 vods 라우트가 `app.state.vod_full_videos` 로 내놓는 조작(같은 작업 슬롯을 쓴다)."""
        return app.state.vod_full_videos

    @app.post("/api/games/{key}/full-video", status_code=202)
    def start_rebuild(key: str):
        """원본 녹화가 남은 옛 게임의 풀영상·후보·마커를 새로 만든다. 저장한 클립은 다시 자르지 않는다."""
        game = load_or_404(key)
        cfg = current_config()
        if game.get("source") == "vod":
            if game.get("fullVideoDeletedAt") or has_full_video(games_dir(key), key):
                raise HTTPException(409, "이미 풀영상이 있거나 자동 정리로 지운 게임입니다")
            vod_control().start(game["vodId"], {int(game["vodGameIndex"])})
            return {"state": "running", "message": "", "fraction": 0.0}
        root = resolve_recording_root(cfg.paths.steam_recording)
        if not can_rebuild(game, games_dir(key), root):
            raise HTTPException(409, "원본 녹화가 남아 있지 않거나 이미 풀영상이 있는 게임입니다")
        if any(j["state"] == "running" for j in rebuild_jobs.values()):
            raise HTTPException(409, "다른 게임의 풀영상을 만드는 중입니다. 끝난 뒤 다시 시도하세요")
        ffmpeg = _ffmpeg()
        job = {"state": "running", "message": "", "fraction": 0.0}
        rebuild_jobs[key] = job
        gdir, cdir = games_dir(key), clips_dir()

        def run() -> None:
            try:
                with activity.registry.track("rebuild-full-video", f"풀영상 만드는 중 ({key})"):
                    rebuild_full_video(
                        games_dir=gdir, clips_dir=cdir, key=key, recording_root=root, cfg=cfg, ffmpeg_path=ffmpeg,
                        on_progress=lambda f: job.update(fraction=f),
                    )
                job.update(state="done", fraction=1.0)
            except RebuildError as exc:
                job.update(state="error", message=str(exc))
            except Exception as exc:
                log.exception("풀영상 만들기 실패: %s", key)
                job.update(state="error", message=f"풀영상을 만들지 못했습니다: {exc}")

        threading.Thread(target=run, daemon=True).start()
        return job

    @app.get("/api/games/{key}/full-video/status")
    def rebuild_status(key: str):
        game = load_or_404(key)
        if game.get("source") == "vod":
            return vod_control().status(game["vodId"], int(game["vodGameIndex"]))
        return rebuild_jobs.get(key) or {"state": "idle", "message": "", "fraction": 0.0}

    reanalyze_jobs: dict[str, dict] = {}

    @app.get("/api/games/{key}/reanalyze")
    def reanalyze_plan(key: str):
        """다시 분석하면 무엇을 하는지: full(원본 녹화에서 풀영상·후보 전부), candidates(원본이 없어 풀영상에서 후보만), None(불가)."""
        game = load_or_404(key)
        if game.get("source") == "vod":
            return {"mode": None}
        root = resolve_recording_root(current_config().paths.steam_recording)
        return {"mode": reanalyze_mode(game, games_dir(key), root)}

    @app.post("/api/games/{key}/reanalyze", status_code=202)
    def start_reanalyze(key: str):
        """게임의 풀영상·후보·결과·초상화를 다시 만든다(원본이 없으면 풀영상에서 후보만). 한 번에 하나만 돈다."""
        game = load_or_404(key)
        if game.get("source") == "vod":
            raise HTTPException(409, "영상 파일 게임은 영상 묶음에서 다시 분석합니다")
        if any(j["state"] == "running" for j in [*rebuild_jobs.values(), *reanalyze_jobs.values()]):
            raise HTTPException(409, "다른 게임을 처리하는 중입니다. 끝난 뒤 다시 시도하세요")
        cfg = current_config()
        ffmpeg = _ffmpeg()
        resolved = resolve_paths(cfg.paths)
        root = resolve_recording_root(cfg.paths.steam_recording)
        job = {"state": "running", "message": "", "fraction": 0.0, "mode": reanalyze_mode(game, games_dir(key), root)}
        reanalyze_jobs[key] = job
        gdir, cdir, staging = games_dir(key), clips_dir(), resolved.staging_games

        def run() -> None:
            try:
                with activity.registry.track("reanalyze-game", f"게임 다시 분석 중 ({key})"):
                    job["mode"] = reanalyze_game(
                        games_dir=gdir, clips_dir=cdir, key=key, recording_root=root, cfg=cfg, ffmpeg_path=ffmpeg,
                        staging_dir=staging, on_progress=lambda f: job.update(fraction=f),
                    )
                job.update(state="done", fraction=1.0)
            except (ReanalyzeError, RebuildError) as exc:
                job.update(state="error", message=str(exc))
            except Exception as exc:
                log.exception("게임 다시 분석 실패: %s", key)
                job.update(state="error", message=f"다시 분석에 실패했습니다: {exc}")
            finally:
                cleanup_preview_registry.notify_clips_changed()

        threading.Thread(target=run, daemon=True).start()
        return job

    @app.get("/api/games/{key}/reanalyze/status")
    def reanalyze_status(key: str):
        load_or_404(key)
        return reanalyze_jobs.get(key) or {"state": "idle", "message": "", "fraction": 0.0, "mode": None}

    @app.get("/api/games/{key}/video")
    def get_game_video(key: str):
        load_or_404(key)
        path = game_dir(games_dir(key), key) / FULL_VIDEO
        if not path.is_file():
            raise HTTPException(404, "풀영상이 없습니다(자동 정리로 지워졌거나 저장하지 못했습니다)")
        return FileResponse(path, media_type="video/mp4")

    @app.get("/api/games/{key}/asset/{name}")
    def get_game_asset(key: str, name: str):
        load_or_404(key)
        if name not in _ASSETS:
            raise HTTPException(404, "파일을 찾을 수 없습니다")
        path = game_dir(games_dir(key), key) / name
        if not path.is_file():
            raise HTTPException(404, "파일을 찾을 수 없습니다")
        return FileResponse(path, media_type="image/jpeg")

    @app.patch("/api/games/{key}")
    def patch_game(key: str, body: GamePatch):
        load_or_404(key)
        if body.pinned is not None:
            update_game(games_dir(key), key, lambda d: d.update(pinned=body.pinned))
            cleanup_preview_registry.notify_clips_changed()
        return _summary(load_or_404(key), games_dir(key))

    def _rename_saved_clip(game: dict, cand: dict) -> None:
        clip_id = (cand.get("user") or {}).get("savedClipId")
        path = clips_dir_for(game) / f"{clip_id}.json" if clip_id else None
        if path is None or not path.is_file():
            return
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
            meta["title"] = gcand.effective_title(cand)
            path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, ValueError):
            pass

    @app.patch("/api/games/{key}/candidates/{candidate_id}")
    def patch_candidate(key: str, candidate_id: str, body: dict):
        game = load_or_404(key)
        if gcand.find_candidate(game, candidate_id) is None:
            raise HTTPException(404, "후보를 찾을 수 없습니다")
        error: list[str] = []

        def change(data: dict) -> None:
            cand = gcand.find_candidate(data, candidate_id)
            try:
                gcand.apply_edit(cand, body, duration_of(data))
            except ValueError as exc:
                error.append(str(exc))

        updated = update_game(games_dir(key), key, change)
        if error:
            raise HTTPException(400, error[0])
        result = gcand.find_candidate(updated, candidate_id)
        if "title" in body:
            _rename_saved_clip(updated, result)
        return result

    @app.post("/api/games/{key}/candidates", status_code=201)
    def add_candidate(key: str, body: CandidateCreate):
        game = load_or_404(key)
        if not game.get("fullVideo"):
            raise HTTPException(409, "풀영상이 없어 구간을 추가할 수 없습니다")
        made: list[dict] = []
        error: list[str] = []

        def change(data: dict) -> None:
            try:
                cand = gcand.new_user_candidate(data, body.start, body.end, duration_of(data), title=body.title)
            except ValueError as exc:
                error.append(str(exc))
                return
            data.setdefault("userCandidates", []).append(cand)
            made.append(cand)

        update_game(games_dir(key), key, change)
        if error:
            raise HTTPException(400, error[0])
        return made[0]

    @app.delete("/api/games/{key}/candidates/{candidate_id}")
    def delete_candidate(key: str, candidate_id: str):
        load_or_404(key)
        removed: list[bool] = []

        def change(data: dict) -> None:
            before = len(data.get("userCandidates") or [])
            data["userCandidates"] = [c for c in data.get("userCandidates") or [] if c.get("id") != candidate_id]
            removed.append(len(data["userCandidates"]) < before)

        update_game(games_dir(key), key, change)
        if not removed[0]:
            raise HTTPException(404, "직접 추가한 구간만 지울 수 있습니다(자동 후보는 '무시'를 쓰세요)")
        return {"id": candidate_id, "deleted": True}

    def _save_one(key: str, candidate_id: str, ffmpeg: Path, category: str | None = None) -> str:
        cfg = current_config()
        game = load_game(games_dir(key), key)
        cand = gcand.find_candidate(game, candidate_id)
        if cand is None:
            raise HTTPException(404, "후보를 찾을 수 없습니다")
        try:
            clip_id = save_and_mark(games_dir(key), key, game, cand, cfg=cfg, ffmpeg_path=ffmpeg, manual=True, category=category)
        except LibraryError as exc:
            raise HTTPException(exc.status, str(exc))
        except FullVideoMissing:
            raise HTTPException(409, "풀영상이 없어 클립을 저장할 수 없습니다")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except (OSError, subprocess.CalledProcessError) as exc:
            raise HTTPException(500, f"클립 저장에 실패했습니다: {describe_clip_error(exc)}")
        cleanup_preview_registry.notify_clips_changed()
        return clip_id

    def _ffmpeg() -> Path:
        ffmpeg = discover_ffmpeg()
        if ffmpeg is None:
            raise HTTPException(503, "ffmpeg를 찾을 수 없습니다")
        return ffmpeg

    @app.post("/api/games/{key}/candidates/{candidate_id}/save")
    def save_candidate(key: str, candidate_id: str, body: SaveOptions | None = None):
        game = load_or_404(key)
        with lock:
            clip_id = _save_one(key, candidate_id, _ffmpeg(), body.category if body else None)
            return {"clipId": clip_id, "category": category_of_clip(game, clip_id)}

    @app.post("/api/games/{key}/save")
    def save_batch(key: str, body: BatchSave):
        game = load_or_404(key)
        try:
            targets = gcand.select_for_batch(game, body.mode, ids=body.ids)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        ffmpeg = _ffmpeg()
        saved: list[dict] = []
        failed: list[dict] = []
        with lock:
            for cand in targets:
                try:
                    saved.append({"candidateId": cand["id"], "clipId": _save_one(key, cand["id"], ffmpeg, body.category)})
                except HTTPException as exc:
                    failed.append({"candidateId": cand["id"], "error": exc.detail})
        return {"saved": saved, "failed": failed}

    def _remove_saved_clip(game: dict, clip_id: str, *, keep_record: bool = True) -> bool:
        """클립 탭 삭제와 같은 처리(라벨 보관·게임 기록 유지). 영상을 못 찾으면(이미 다른 데서 지움) 지운 것으로 세지 않는다."""
        cfg = current_config()
        resolved = resolve_paths(cfg.paths)
        library = clips_dir_for(game)
        clip = find_clip(library, clip_id, resolved.clip_roots)
        if clip is None:
            return False
        proxy = proxy_file(resolved.proxy_cache, clip_id)
        keep_records = keep_record and cfg.retention.keep_game_records and library == resolved.library_steam
        found_video = clip.video.exists()
        delete_clip(
            clip.meta_path, mode=cfg.ui.delete_mode, archive_dir=archive_dir_for(library),
            records_dir=records_dir_for(library) if keep_records else None,
            proxy=proxy if proxy.exists() else None, video=clip.video,
        )
        remove_orphan_result_images(library)
        return found_video

    def _clear_saved_marks(key: str, *, only: str | None = None, dismiss: bool = False) -> None:
        def change(data: dict) -> None:
            for cand in gcand.all_candidates(data):
                user = cand.get("user") or {}
                if only is not None and cand.get("id") != only or not user.get("savedClipId"):
                    continue
                for field in ("savedClipId", "savedStart", "savedEnd"):
                    user.pop(field, None)
                if dismiss:
                    user["dismissed"] = True
                cand["user"] = user

        update_game(games_dir(key), key, change)

    def _remove_game_entirely(game: dict, folder: Path) -> None:
        """게임 폴더(풀영상·게임 기록·결과표·초상화)와 `.games` 기록을 지워 목록에서 사라지게 한다."""
        cfg = current_config()
        if cfg.ui.delete_mode == PERMANENT:
            shutil.rmtree(folder)
        else:
            send_to_recycle_bin([folder])
        if game.get("source") != "vod":
            delete_record(records_dir_for(clips_dir_for(game)), game_key(game.get("sessionDir"), game.get("matchStartUtc")))

    @app.post("/api/games/{key}/delete")
    def delete_game_files(key: str, body: GameDelete):
        """풀영상·저장한 클립을 지운다. 게임 기록(결과·후보)은 남는다. 휴지통/영구는 `ui.deleteMode`."""
        if body.target not in ("fullVideo", "clips", "both", "all"):
            raise HTTPException(400, "target 은 fullVideo, clips, both, all 중 하나여야 합니다")
        game = load_or_404(key)
        folder = game_dir(games_dir(key), key)
        video = folder / FULL_VIDEO
        with lock:
            freed = video.stat().st_size if video.is_file() else 0
            if body.target == "fullVideo" and not video.is_file():
                raise HTTPException(409, "지울 풀영상이 없습니다")
            deleted_clips = 0
            if body.target in ("clips", "both", "all"):
                for cand in gcand.all_candidates(game):
                    clip_id = (cand.get("user") or {}).get("savedClipId")
                    if clip_id and _remove_saved_clip(game, clip_id, keep_record=body.target != "all"):
                        deleted_clips += 1
                if body.target != "all":
                    _clear_saved_marks(key)
            deleted_full = False
            if body.target in ("fullVideo", "both") and video.is_file():
                delete_full_video(folder, mode=current_config().ui.delete_mode)
                deleted_full = True
            if body.target == "all":
                deleted_full = video.is_file()
                _remove_game_entirely(game, folder)
        cleanup_preview_registry.notify_clips_changed()
        return {"deletedFullVideo": deleted_full, "deletedClips": deleted_clips, "freedBytes": freed if deleted_full else 0}

    @app.post("/api/games/{key}/candidates/{candidate_id}/unsave")
    def unsave_candidate(key: str, candidate_id: str):
        """보관 해제: 클립 영상을 지우고 후보를 보관 전 상태로 되돌린다. 삭제·무시가 아니라 후보는 목록에 그대로 남고 고친 범위도 유지된다."""
        game = load_or_404(key)
        cand = gcand.find_candidate(game, candidate_id)
        if cand is None:
            raise HTTPException(404, "후보를 찾을 수 없습니다")
        clip_id = (cand.get("user") or {}).get("savedClipId")
        if not clip_id:
            raise HTTPException(409, "보관한 클립이 아닙니다")
        with lock:
            _remove_saved_clip(game, clip_id)
            _clear_saved_marks(key, only=candidate_id)
        cleanup_preview_registry.notify_clips_changed()
        return gcand.find_candidate(load_or_404(key), candidate_id)
