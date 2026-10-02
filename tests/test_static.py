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


def _client_with_dist(tmp_path: Path) -> TestClient:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist / "assets" / "index-AbC123.js").write_text("1", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    app = create_app(Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp")))
    mount_static(app, dist)
    return TestClient(app)


def test_index_html_is_always_revalidated_so_a_new_install_shows_the_new_screen(tmp_path: Path):
    client = _client_with_dist(tmp_path)

    for path in ("/", "/index.html", "/favicon.svg"):
        assert client.get(path).headers["cache-control"] == "no-cache", path


def test_hashed_assets_are_cached_for_a_year(tmp_path: Path):
    client = _client_with_dist(tmp_path)

    cache = client.get("/assets/index-AbC123.js").headers["cache-control"]

    assert "max-age=31536000" in cache and "immutable" in cache


def test_revalidation_still_answers_304_for_an_unchanged_index(tmp_path: Path):
    client = _client_with_dist(tmp_path)
    first = client.get("/")

    again = client.get("/", headers={"If-None-Match": first.headers["etag"]})

    assert again.status_code == 304
