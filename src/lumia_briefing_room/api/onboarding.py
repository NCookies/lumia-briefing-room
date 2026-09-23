"""첫 실행 화면과 진단 정보 내보내기 API. (plan-deploy.md D3)"""

import os
import platform
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Response

from lumia_briefing_room import __version__, paths
from lumia_briefing_room.appmode import resolve_mode
from lumia_briefing_room.config import Config, dataclass_to_camel_dict, discover_ffmpeg, resolve_paths
from lumia_briefing_room.consent import CONSENT_VERSION, pending_items
from lumia_briefing_room.diagnostics import build_diagnostics_zip
from lumia_briefing_room.logsetup import default_log_path
from lumia_briefing_room.recording_info import find_latest_session
from lumia_briefing_room.resolution_support import classify_resolution
from lumia_briefing_room.steam_paths import discover_recording_root


def _recording_report(cfg: Config) -> dict:
    root = cfg.paths.steam_recording
    source = "config" if root else None
    if root is None:
        root = discover_recording_root()
        source = "auto" if root else None
    exists = bool(root) and Path(root).is_dir()
    session = find_latest_session(Path(root)) if exists else None
    resolution = classify_resolution(session.width, session.height) if session else None
    return {
        "root": str(root) if root else None,
        "source": source,
        "exists": exists,
        "session": (
            {"name": session.name, "width": session.width, "height": session.height, "codec": session.codec}
            if session
            else None
        ),
        "resolution": (
            {
                "kind": resolution.kind,
                "message": resolution.message,
                "width": resolution.width,
                "height": resolution.height,
            }
            if resolution
            else None
        ),
    }


def _user_names() -> list[str]:
    return [os.environ.get("USERNAME", ""), Path.home().name]


def register_onboarding_routes(
    app: FastAPI, *, current_config: Callable[[], Config], put_config: Callable[[dict], dict]
) -> None:
    @app.get("/api/first-run")
    def get_first_run():
        cfg = current_config()
        answered = cfg.consent.version
        pending = pending_items(answered)
        return {
            "needed": bool(pending),
            "pendingItems": [item.key for item in pending],
            "answeredVersion": answered,
            "currentVersion": CONSENT_VERSION,
            "recording": _recording_report(cfg),
            "clipsDir": str(resolve_paths(cfg.paths).clips),
            "ffmpegFound": discover_ffmpeg() is not None,
        }

    @app.post("/api/first-run/complete")
    def complete_first_run():
        answered = current_config().consent.version
        version = max(answered, CONSENT_VERSION)
        put_config({"consent": {"version": version}})
        return {"consentVersion": version}

    @app.get("/api/diagnostics")
    def get_diagnostics():
        cfg = current_config()
        frozen = paths.is_frozen()
        ffmpeg = discover_ffmpeg()
        info = {
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "version": __version__,
            "mode": resolve_mode(cfg.app.mode, frozen=frozen),
            "frozen": frozen,
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "ffmpeg": str(ffmpeg) if ffmpeg else None,
            "consentVersion": cfg.consent.version,
            "recording": _recording_report(cfg),
        }
        log_dir = app.state.log_dir or default_log_path().parent
        data = build_diagnostics_zip(
            log_dir=Path(log_dir),
            info=info,
            config=dataclass_to_camel_dict(cfg),
            usernames=_user_names(),
            nicknames=[cfg.player.nickname],
        )
        filename = f"lumia-diagnostics-{datetime.now():%Y%m%d-%H%M%S}.zip"
        return Response(
            content=data,
            media_type="application/zip",
            headers={"content-disposition": f'attachment; filename="{filename}"'},
        )
