"""개발 모드 전용 관리자 API: 서버에 쌓인 라벨 집계·검색. (plan-infra.md §8)

배포 모드에서는 요청마다 404 로 막는다(설정 `app.mode` 가 바뀌어도 그대로 따른다). 토큰은 서버(이 프로세스)만 갖는다.
"""

from __future__ import annotations

import threading

from fastapi import FastAPI, HTTPException, Query

from lumia_briefing_room import admin_labels, paths
from lumia_briefing_room.appmode import resolve_mode

MAX_LIMIT = 500
MODE_PATTERN = "^(release|dev)$"


def register_admin_routes(app: FastAPI, *, current_config) -> None:
    cache: dict[str, list[dict]] = {}
    lock = threading.Lock()

    def client():
        injected = getattr(app.state, "admin_client", None)
        if injected is not None:
            return injected
        url, token = admin_labels.read_credentials()
        if not token:
            raise HTTPException(503, f"관리자 토큰이 없습니다. 저장소 루트 .env 에 {admin_labels.TOKEN_ENV} 를 넣고 앱을 다시 실행하세요")
        if not url:
            raise HTTPException(503, f"서버 주소가 없습니다. 저장소 루트 .env 에 {admin_labels.URL_ENV} 를 넣고 앱을 다시 실행하세요")
        return admin_labels.make_client(url, token)

    def load(mode: str, refresh: bool) -> list[dict]:
        if resolve_mode(current_config().app.mode, frozen=paths.is_frozen()) != "dev":
            raise HTTPException(404, "Not Found")
        with lock:
            if refresh or mode not in cache:
                http = client()
                try:
                    cache[mode] = admin_labels.fetch_all(http, mode)
                except admin_labels.AdminError as exc:
                    raise HTTPException(502, str(exc)) from exc
                finally:
                    if getattr(app.state, "admin_client", None) is None:
                        http.close()
            return cache[mode]

    @app.get("/api/admin/summary")
    def get_summary(mode: str = Query("release", pattern=MODE_PATTERN), refresh: bool = False):
        return admin_labels.summarize(load(mode, refresh))

    @app.get("/api/admin/labels")
    def get_labels(
        mode: str = Query("release", pattern=MODE_PATTERN),
        q: str = "",
        userLabel: str = "",
        limit: int = Query(100, ge=1, le=MAX_LIMIT),
        offset: int = Query(0, ge=0),
    ):
        found = admin_labels.filter_items(load(mode, False), q, userLabel)
        found.sort(key=lambda it: it.get("receivedAt") or "", reverse=True)
        return {"total": len(found), "items": found[offset : offset + limit]}
