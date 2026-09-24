import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room import native_dialog
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig


@pytest.fixture
def client(tmp_path):
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp"))
    return TestClient(create_app(cfg, config_path=tmp_path / "config.json"))


def test_pick_folder_returns_chosen_path(client, monkeypatch):
    seen = {}

    def fake(initial="", title=""):
        seen.update(initial=initial, title=title)
        return r"D:\clips"

    monkeypatch.setattr(native_dialog, "pick_folder", fake)

    resp = client.post("/api/fs/pick-folder", json={"initial": r"C:\start", "title": "고르기"})

    assert resp.json() == {"path": r"D:\clips"}
    assert seen == {"initial": r"C:\start", "title": "고르기"}


def test_pick_folder_cancel_returns_null(client, monkeypatch):
    monkeypatch.setattr(native_dialog, "pick_folder", lambda initial="", title="": None)

    assert client.post("/api/fs/pick-folder", json={}).json() == {"path": None}


def test_pick_videos_returns_paths(client, monkeypatch):
    monkeypatch.setattr(native_dialog, "pick_video_files", lambda initial="", title="": ["a.mp4", "b.mkv"])

    assert client.post("/api/fs/pick-videos", json={}).json() == {"paths": ["a.mp4", "b.mkv"]}


def test_dialog_failure_is_reported(client, monkeypatch):
    def boom(initial="", title=""):
        raise OSError("no dialog")

    monkeypatch.setattr(native_dialog, "pick_folder", boom)

    resp = client.post("/api/fs/pick-folder", json={})

    assert resp.status_code == 500
    assert "no dialog" in resp.json()["detail"]
