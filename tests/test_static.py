from pathlib import Path

from fastapi.testclient import TestClient

from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.api.static import find_frontend_dist, mount_static
from lumia_briefing_room.config import Config, PathsConfig


def test_find_frontend_dist_found(tmp_path: Path):
    nested = tmp_path / "src" / "lumia_briefing_room" / "api"
    nested.mkdir(parents=True)
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")

    assert find_frontend_dist(nested) == dist


def test_find_frontend_dist_missing(tmp_path: Path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    assert find_frontend_dist(nested) is None


def test_find_frontend_dist_ignores_dist_without_index(tmp_path: Path):
    nested = tmp_path / "src"
    nested.mkdir(parents=True)
    (tmp_path / "frontend" / "dist").mkdir(parents=True)

    assert find_frontend_dist(nested) is None


def test_mount_static_serves_index_and_keeps_api_routes(tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>루미아</body></html>", encoding="utf-8")
    (dist / "app.js").write_text("console.log('hi')", encoding="utf-8")

    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp"))
    app = create_app(cfg)
    mount_static(app, dist)
    client = TestClient(app)

    root = client.get("/")
    assert root.status_code == 200
    assert "루미아" in root.text

    asset = client.get("/app.js")
    assert asset.status_code == 200
    assert "console.log" in asset.text

    api = client.get("/api/clips")
    assert api.status_code == 200
    assert api.json() == []


def test_find_frontend_dist_default_uses_resource_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LUMIA_RESOURCE_DIR", str(tmp_path))
    assert find_frontend_dist() is None

    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    assert find_frontend_dist() == dist
