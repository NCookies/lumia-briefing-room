"""빌드된 프론트엔드(frontend/dist)를 FastAPI 에 정적으로 얹는다. (plan-ui.md §4-1)"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def find_frontend_dist(start: Path | None = None) -> Path | None:
    base = Path(start) if start is not None else Path(__file__).resolve()
    for parent in [base, *base.parents]:
        candidate = parent / "frontend" / "dist"
        if (candidate / "index.html").exists():
            return candidate
    return None


def mount_static(app: FastAPI, dist_dir: Path) -> None:
    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")
