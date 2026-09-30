"""게임(풀영상) API. (plan-fullvideo.md §3.6, F4)

기존 클립 API 는 그대로 두고 새 경로만 추가한다(UI 를 되돌릴 수 있게, plan §5). 사용자 수정은 `game.json` 의
`candidates[].user` 에만 쓰고 자동 검출 값은 건드리지 않는다.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from lumia_briefing_room.config import Config, discover_ffmpeg, resolve_paths
from lumia_briefing_room.pipeline import game_candidates as gcand
from lumia_briefing_room.pipeline.clip_from_full import FullVideoMissing, save_candidate_clip
from lumia_briefing_room.pipeline.cleanup_registry import registry as cleanup_preview_registry
from lumia_briefing_room.pipeline.ffmpeg_errors import describe_clip_error
from lumia_briefing_room.pipeline.game_files import GameNotFound, game_dir, has_full_video, list_games, load_game, update_game
from lumia_briefing_room.pipeline.game_store import FULL_VIDEO
from lumia_briefing_room.pipeline.legacy_games import migrate_legacy_games

log = logging.getLogger(__name__)

_ASSETS = {"result.jpg", "portrait_me.jpg", "portrait_teammate1.jpg", "portrait_teammate2.jpg"}


class GamePatch(BaseModel):
    pinned: bool | None = None


class CandidateCreate(BaseModel):
    start: float
    end: float
    title: str | None = None


class BatchSave(BaseModel):
    mode: str = "all"  # all | certain | ids
    ids: list[str] | None = None


def _summary(game: dict, games_dir: Path) -> dict:
    cands = gcand.all_candidates(game)
    active = [c for c in cands if not (c.get("user") or {}).get("dismissed")]
    video = game.get("fullVideo") or {}
    return {
        "key": game["gameKey"],
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
        "fullVideoDeletedAt": game.get("fullVideoDeletedAt"),
        "candidateCount": len(active),
        "certainCount": sum(1 for c in active if c.get("certain")),
        "savedClipCount": sum(1 for c in cands if (c.get("user") or {}).get("savedClipId")),
        "unsavedEditCount": sum(1 for c in active if gcand.range_changed(c, float(video.get("durationSec") or 0.0))),
    }


def register_game_routes(
    app: FastAPI, *, lock, current_config: Callable[[], Config]
) -> None:
    migrate_lock = threading.Lock()

    def games_dir() -> Path:
        return resolve_paths(current_config().paths).games

    def clips_dir() -> Path:
        return resolve_paths(current_config().paths).clips

    migrated: set[tuple[Path, Path]] = set()

    def migrate_once() -> None:
        """앱을 켠 뒤 처음 목록을 볼 때(경로를 바꾸면 그 경로에서 다시 한 번) 이전 버전 클립을 게임 기록으로 옮긴다.

        시작 시 자동보다 목록 요청 때가 안전하다: 경로를 옵션에서 바꾼 뒤에도 따라가고, 서버가 뜨는 동안 파일을 건드리지 않는다.
        """
        pair = (clips_dir(), games_dir())
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
            return load_game(games_dir(), key)
        except GameNotFound:
            raise HTTPException(404, "게임을 찾을 수 없습니다")

    def duration_of(game: dict) -> float:
        video = game.get("fullVideo") or {}
        return float(video.get("durationSec") or 0.0)

    @app.get("/api/games")
    def get_games():
        migrate_once()
        root = games_dir()
        return {"games": [_summary(g, root) for g in list_games(root)]}

    @app.get("/api/games/{key}")
    def get_game(key: str):
        game = load_or_404(key)
        return {**game, "hasFullVideo": has_full_video(games_dir(), key)}

    @app.get("/api/games/{key}/video")
    def get_game_video(key: str):
        load_or_404(key)
        path = game_dir(games_dir(), key) / FULL_VIDEO
        if not path.is_file():
            raise HTTPException(404, "풀영상이 없습니다(자동 정리로 지워졌거나 저장하지 못했습니다)")
        return FileResponse(path, media_type="video/mp4")

    @app.get("/api/games/{key}/asset/{name}")
    def get_game_asset(key: str, name: str):
        load_or_404(key)
        if name not in _ASSETS:
            raise HTTPException(404, "파일을 찾을 수 없습니다")
        path = game_dir(games_dir(), key) / name
        if not path.is_file():
            raise HTTPException(404, "파일을 찾을 수 없습니다")
        return FileResponse(path, media_type="image/jpeg")

    @app.patch("/api/games/{key}")
    def patch_game(key: str, body: GamePatch):
        load_or_404(key)
        if body.pinned is not None:
            update_game(games_dir(), key, lambda d: d.update(pinned=body.pinned))
            cleanup_preview_registry.notify_clips_changed()
        return _summary(load_or_404(key), games_dir())

    def _rename_saved_clip(cand: dict) -> None:
        clip_id = (cand.get("user") or {}).get("savedClipId")
        path = clips_dir() / f"{clip_id}.json" if clip_id else None
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

        updated = update_game(games_dir(), key, change)
        if error:
            raise HTTPException(400, error[0])
        result = gcand.find_candidate(updated, candidate_id)
        if "title" in body:
            _rename_saved_clip(result)
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

        update_game(games_dir(), key, change)
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

        update_game(games_dir(), key, change)
        if not removed[0]:
            raise HTTPException(404, "직접 추가한 구간만 지울 수 있습니다(자동 후보는 '무시'를 쓰세요)")
        return {"id": candidate_id, "deleted": True}

    def _save_one(key: str, candidate_id: str, ffmpeg: Path) -> str:
        cfg = current_config()
        game = load_game(games_dir(), key)
        cand = gcand.find_candidate(game, candidate_id)
        if cand is None:
            raise HTTPException(404, "후보를 찾을 수 없습니다")
        user = cand.get("user") or {}
        existing = user.get("savedClipId")
        used = gcand.effective_range(cand, duration_of(game))
        if existing and not gcand.range_changed(cand, duration_of(game)):
            return existing
        try:
            clip_id = save_candidate_clip(
                game, cand, game_folder=game_dir(games_dir(), key), clips_dir=clips_dir(), cfg=cfg, ffmpeg_path=ffmpeg,
                replace_clip_id=existing,
            )
        except FullVideoMissing:
            raise HTTPException(409, "풀영상이 없어 클립을 저장할 수 없습니다")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except (OSError, subprocess.CalledProcessError) as exc:
            raise HTTPException(500, f"클립 저장에 실패했습니다: {describe_clip_error(exc)}")

        def mark(data: dict) -> None:
            target = gcand.find_candidate(data, candidate_id)
            target["user"] = {
                **(target.get("user") or {}),
                "savedClipId": clip_id,
                "savedStart": round(used[0], 3),
                "savedEnd": round(used[1], 3),
            }

        update_game(games_dir(), key, mark)
        cleanup_preview_registry.notify_clips_changed()
        return clip_id

    def _ffmpeg() -> Path:
        ffmpeg = discover_ffmpeg()
        if ffmpeg is None:
            raise HTTPException(503, "ffmpeg를 찾을 수 없습니다")
        return ffmpeg

    @app.post("/api/games/{key}/candidates/{candidate_id}/save")
    def save_candidate(key: str, candidate_id: str):
        load_or_404(key)
        with lock:
            return {"clipId": _save_one(key, candidate_id, _ffmpeg())}

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
                    saved.append({"candidateId": cand["id"], "clipId": _save_one(key, cand["id"], ffmpeg)})
                except HTTPException as exc:
                    failed.append({"candidateId": cand["id"], "error": exc.detail})
        return {"saved": saved, "failed": failed}
