"""앱 안에서 보여 주는 패치노트 API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException

from lumia_briefing_room import paths
from lumia_briefing_room.changelog import parse_changelog


def changelog_path() -> Path:
    return paths.resource_dir() / "CHANGELOG.md"


def register_app_info_routes(app: FastAPI) -> None:
    @app.get("/api/changelog")
    def get_changelog():
        try:
            text = changelog_path().read_text(encoding="utf-8")
        except OSError:
            raise HTTPException(404, "패치노트를 찾을 수 없습니다")
        return {"releases": parse_changelog(text)}
