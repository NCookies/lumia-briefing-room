"""과거 녹화 전체 분석 API. (plan-backfill.md B5)

분석은 백그라운드 스레드에서 돌고, 화면은 상태를 폴링한다. 취소는 프레임 사이에서 즉시 먹고,
끝낸 경기는 상태 파일에 남으므로 다시 시작하면 이어서 한다.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException

from lumia_briefing_room.config import Config, discover_ffmpeg, resolve_paths
from lumia_briefing_room.pipeline.backfill import (
    BackfillProgress,
    BackfillResult,
    collect_known_starts,
    run_backfill,
)
from lumia_briefing_room.pipeline.backfill_runtime import (
    SteamSessionScanner,
    estimate_backfill,
    make_process_window,
)
from lumia_briefing_room.steam_paths import resolve_recording_root

log = logging.getLogger("lumia_briefing_room.backfill")

STATE_DIRNAME = "backfill"
STAGING_DIRNAME = "backfill_staging"


def collect_log_starts(cfg: Config) -> list[datetime]:
    """Player.log 로 아는 경기의 시작 시각. 아직 처리 안 된 것도 포함한다 — 곧 감시가 만들 경기를 여기서 또 만들지 않게."""
    try:
        from lumia_briefing_room.api.app import read_boundaries

        return [m.start_utc for m in read_boundaries(cfg)]
    except Exception:
        log.warning("Player.log 를 읽지 못해 로그 기준 중복 제외는 건너뛴다", exc_info=True)
        return []


def _dirs(cfg: Config) -> tuple[Path, Path, Path]:
    resolved = resolve_paths(cfg.paths)
    return resolved.clips, resolved.temp / STATE_DIRNAME, resolved.temp / STAGING_DIRNAME


def _result_dict(result: BackfillResult | None) -> dict | None:
    if result is None:
        return None
    return {
        "sessionsScanned": result.sessions_scanned,
        "gamesFound": result.games_found,
        "gamesProcessed": result.games_processed,
        "gamesFailed": result.games_failed,
        "clipsCreated": result.clips_created,
        "cancelled": result.cancelled,
        "skipped": {
            "known": result.skipped["known"],
            "cutAtStart": result.skipped["cut_at_start"],
            "stillRunning": result.skipped["still_running"],
            "alreadyDone": result.skipped["already_done"],
            "gaveUp": result.skipped["gave_up"],
        },
    }


def register_backfill_routes(app: FastAPI, *, current_config: Callable[[], Config]) -> None:
    lock = threading.Lock()
    job: dict = {"state": "idle"}
    cancel = threading.Event()

    def snapshot() -> dict:
        with lock:
            return dict(job)

    def update(**fields) -> None:
        with lock:
            job.update(fields)

    def on_progress(p: BackfillProgress) -> None:
        update(
            phase=p.phase, fraction=p.fraction, message=p.message, sessionIndex=p.session_index,
            sessionTotal=p.session_total, gamesDone=p.games_done, gamesTotal=p.games_total, clips=p.clips,
        )

    @app.get("/api/backfill")
    def status():
        return snapshot()

    @app.get("/api/backfill/preview")
    def preview():
        cfg = current_config()
        root = resolve_recording_root(cfg.paths.steam_recording)
        base = {"recordingRoot": str(root) if root else None, "canStart": False, "reason": None}
        if root is None:
            return {**base, "reason": "스팀 녹화 폴더를 찾지 못했습니다. 옵션에서 녹화 폴더를 먼저 지정해 주세요."}
        info = estimate_backfill(root, _dirs(cfg)[1])
        base.update(info)
        if info["sessions"] == 0:
            return {**base, "reason": "분석할 이터널 리턴 녹화가 없습니다."}
        if discover_ffmpeg() is None:
            return {**base, "reason": "ffmpeg 를 찾지 못했습니다."}
        return {**base, "canStart": True}

    @app.post("/api/backfill/start", status_code=202)
    def start():
        cfg = current_config()
        with lock:
            if job.get("state") == "running":
                raise HTTPException(409, "이미 분석하는 중입니다")
        ffmpeg = discover_ffmpeg()
        if ffmpeg is None:
            raise HTTPException(503, "ffmpeg를 찾을 수 없습니다")
        root = resolve_recording_root(cfg.paths.steam_recording)
        if root is None:
            raise HTTPException(503, "스팀 녹화 폴더를 찾을 수 없습니다")

        clips_dir, state_dir, staging_root = _dirs(cfg)
        cancel.clear()
        with lock:
            job.clear()
            job.update(
                state="running", phase="scan", fraction=0.0, message="", sessionIndex=0, sessionTotal=0,
                gamesDone=0, gamesTotal=0, clips=0, error=None, result=None,
                startedAt=datetime.now(timezone.utc).isoformat(),
            )

        def run() -> None:
            try:
                scanner = SteamSessionScanner(root, ffmpeg, state_dir=state_dir, hwaccel=cfg.vod.hwaccel)
                process = make_process_window(
                    cfg, ffmpeg, game_mode="battle_royale", k_templates=None, a_templates=None,
                    hwaccel=cfg.vod.hwaccel, config_path=app.state.config_path,
                )
                known = collect_known_starts(clips_dir) + collect_log_starts(cfg)
                result = run_backfill(
                    scanner=scanner, process_window=process, clips_dir=clips_dir, state_dir=state_dir,
                    staging_root=staging_root, known_starts=known, cancel=cancel, on_progress=on_progress,
                )
            except Exception as exc:
                log.exception("과거 녹화 분석 실패")
                update(state="error", error=str(exc) or type(exc).__name__)
                return
            update(
                state="cancelled" if result.cancelled else "done",
                result=_result_dict(result),
                **({} if result.cancelled else {"fraction": 1.0}),
            )

        threading.Thread(target=run, daemon=True).start()
        return {"state": "running"}

    @app.post("/api/backfill/cancel")
    def cancel_run():
        if snapshot().get("state") == "running":
            cancel.set()
        return snapshot()
