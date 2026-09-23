from pathlib import Path

from fastapi.testclient import TestClient

import lumia_briefing_room
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config


def test_app_info_returns_package_version():
    resp = TestClient(create_app(Config())).get("/api/app-info")
    assert resp.status_code == 200
    assert resp.json()["version"] == lumia_briefing_room.__version__


def test_pyproject_reads_version_from_package():
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in pyproject
    assert 'attr = "lumia_briefing_room.__version__"' in pyproject
