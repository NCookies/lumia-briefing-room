"""저장 공간·앱 알림 API. (plan-fullvideo.md §3.4)"""

from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from lumia_briefing_room.config import Config, resolve_paths
from lumia_briefing_room.pipeline import disk_alert
from lumia_briefing_room.pipeline.disk_space import GB, RECOMMENDED_GB
from lumia_briefing_room.pipeline.notices import notices


def disk_report(cfg: Config) -> dict:
    """저장 폴더가 있는 드라이브의 여유 공간. 잴 수 없으면 `available: false`."""
    try:
        status = disk_alert.disk_status(cfg)
    except OSError:
        return {"available": False, "recommendedGb": list(RECOMMENDED_GB)}
    return {
        "available": True,
        "path": str(resolve_paths(cfg.paths).games_steam),
        "freeBytes": status.free_bytes,
        "freeGb": round(status.free_bytes / GB, 1),
        "expectedGameBytes": status.expected_bytes,
        "thresholdBytes": status.threshold_bytes,
        "low": status.low,
        "belowRecommended": status.free_bytes < RECOMMENDED_GB[0] * GB,
        "message": status.message,
        "recommendedGb": list(RECOMMENDED_GB),
    }


def register_disk_routes(app: FastAPI, *, current_config: Callable[[], Config]) -> None:
    @app.get("/api/disk")
    def get_disk():
        return disk_report(current_config())

    @app.get("/api/notices")
    def get_notices():
        return {"notices": notices.list()}

    @app.post("/api/notices/{kind}/dismiss")
    def dismiss_notice(kind: str):
        if not any(n["kind"] == kind for n in notices.list()):
            raise HTTPException(404, "알림을 찾을 수 없습니다")
        notices.clear(kind)
        return {"kind": kind, "dismissed": True}
