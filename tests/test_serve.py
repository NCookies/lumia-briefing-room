from pathlib import Path

from fastapi.testclient import TestClient

from lumia_briefing_room.cli.serve import build_app, wait_until_started
from lumia_briefing_room.config import Config, PathsConfig


def test_build_app_without_frontend_dist_serves_api_only(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("lumia_briefing_room.cli.serve.find_frontend_dist", lambda start=None: None)
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp"))

    app = build_app(cfg)
    client = TestClient(app)

    assert client.get("/api/clips").status_code == 200
    assert client.get("/").status_code == 404


def test_build_app_with_frontend_dist_serves_both(tmp_path: Path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr("lumia_briefing_room.cli.serve.find_frontend_dist", lambda start=None: dist)
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp"))

    app = build_app(cfg)
    client = TestClient(app)

    assert client.get("/").status_code == 200
    assert client.get("/api/clips").status_code == 200


def test_wait_until_started_returns_true_once_flag_set():
    class FakeServer:
        def __init__(self):
            self.started = False

    server = FakeServer()
    calls = []

    def fake_sleep(sec):
        calls.append(sec)
        server.started = True

    assert wait_until_started(server, timeout=1.0, sleep=fake_sleep) is True
    assert calls == [0.05]


def test_wait_until_started_times_out():
    class FakeServer:
        started = False

    ticks = iter([0.0, 0.5, 1.0, 1.5])

    assert (
        wait_until_started(
            FakeServer(), timeout=1.0, sleep=lambda _sec: None, now=lambda: next(ticks)
        )
        is False
    )
