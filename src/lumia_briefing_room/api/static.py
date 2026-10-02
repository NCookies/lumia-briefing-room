"""빌드된 프론트엔드(frontend/dist)를 FastAPI 에 정적으로 얹는다. (plan-ui.md §4-1)"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from lumia_briefing_room import paths


def find_frontend_dist(start: Path | None = None) -> Path | None:
    if start is None:
        dist = paths.frontend_dist_dir()
        return dist if (dist / "index.html").exists() else None
    base = Path(start)
    for parent in [base, *base.parents]:
        candidate = parent / "frontend" / "dist"
        if (candidate / "index.html").exists():
            return candidate
    return None


class FrontendFiles(StaticFiles):
    """`assets/` 는 파일 이름에 내용 해시가 들어 있어 오래 캐시하고, 나머지(`index.html` 등)는 매번 다시 확인한다.

    캐시 헤더가 없으면 브라우저가 `index.html` 을 수정 시각으로 어림잡아 한동안 재사용해, 앱을 지우고 새로 설치해도 옛 화면이 보였다."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            hashed = path.replace("\\", "/").startswith("assets/")
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable" if hashed else "no-cache"
        return response


def mount_static(app: FastAPI, dist_dir: Path) -> None:
    app.mount("/", FrontendFiles(directory=str(dist_dir), html=True), name="frontend")
