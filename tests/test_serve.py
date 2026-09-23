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


def test_server_starts_when_there_is_no_console(tmp_path: Path, monkeypatch):
    """--noconsole 빌드에서는 sys.stdout 이 None 이라 uvicorn 의 기본 로깅 설정이 터진다.

    실측(빌드본 로그): ColourizedFormatter 가 sys.stdout.isatty() 를 불러
    AttributeError → ValueError: Unable to configure formatter 'default' 로 서버가 아예 안 떴다.
    """
    import socket
    import sys

    from lumia_briefing_room.cli.serve import run_server_in_thread
    from lumia_briefing_room.config import Config, PathsConfig

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp"))
    server, thread = run_server_in_thread(build_app(cfg), port=port)
    try:
        assert wait_until_started(server, timeout=10) is True
    finally:
        server.should_exit = True
        thread.join(timeout=10)
