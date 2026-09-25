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


def test_video_formats_have_a_single_source_shared_by_scan_dialog_and_screen():
    from lumia_briefing_room import native_dialog, video_formats
    from lumia_briefing_room.api import vods

    assert vods.VIDEO_EXTENSIONS is video_formats.VIDEO_EXTENSIONS
    assert video_formats.VERIFIED_EXTENSIONS <= video_formats.VIDEO_EXTENSIONS
    assert native_dialog.video_patterns() == ";".join(f"*{ext}" for ext in video_formats.sorted_extensions())


def test_app_info_lists_supported_and_verified_video_formats():
    from lumia_briefing_room import video_formats

    body = TestClient(create_app(Config())).get("/api/app-info").json()
    assert body["videoFormats"]["supported"] == video_formats.sorted_extensions()
    assert body["videoFormats"]["verified"] == sorted(video_formats.VERIFIED_EXTENSIONS)
    assert ".mp4" in body["videoFormats"]["verified"]
