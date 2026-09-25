"""업데이트 상태·수동 확인·설치 API. (plan-deploy.md D9)

확인과 설치는 사용자가 직접 누르는 동작이라 `update.check` 값과 무관하게 동작한다.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from lumia_briefing_room.updater import Updater


def register_update_routes(app: FastAPI) -> None:
    def updater() -> Updater:
        current = getattr(app.state, "updater", None)
        if current is None:
            current = Updater(
                config_path=app.state.config_path,
                on_launched=getattr(app.state, "on_update_launched", None),
            )
            app.state.updater = current
        return current

    @app.get("/api/update/status")
    def get_status():
        return updater().status()

    @app.post("/api/update/check")
    def post_check():
        return updater().check()

    @app.post("/api/update/install")
    def post_install():
        started = updater().start_install()
        return JSONResponse(updater().status() | {"started": started}, status_code=202)
