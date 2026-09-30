import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room import activity
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig, load_config, resolve_paths, save_config
from lumia_briefing_room.pipeline.library_startup import adopt_default_root

KEY = "20260928_160025"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))


def make_legacy(tmp_path):
    base = tmp_path / "old"
    cfg = Config(paths=PathsConfig(clips=base / "clips", vod_clips=base / "vod", games=base / "games", temp=tmp_path / "tmp"))
    resolved = resolve_paths(cfg.paths)
    (base / "clips").mkdir(parents=True)
    (base / "clips" / "a.mp4").write_bytes(b"VIDEO")
    resolved.library_steam.mkdir(parents=True)
    (resolved.library_steam / "a.json").write_text(json.dumps({"title": "a"}), encoding="utf-8")
    (base / "games" / KEY).mkdir(parents=True)
    (base / "games" / KEY / "full.mp4").write_bytes(b"FULL")
    (base / "games" / KEY / "game.json").write_text(
        json.dumps({"gameKey": KEY, "fullVideo": {"sizeBytes": 4}, "candidates": []}), encoding="utf-8"
    )
    path = tmp_path / "config.json"
    save_config(cfg, path)
    return TestClient(create_app(cfg, config_path=path)), path


def run_move(client, body):
    resp = client.post("/api/storage/migrate", json=body)
    if resp.status_code != 202:
        return resp, None
    deadline = time.time() + 10
    while time.time() < deadline:
        status = client.get("/api/storage/migrate").json()
        if status["state"] != "running":
            return resp, status
        time.sleep(0.02)
    raise AssertionError("이동이 끝나지 않았다")


def test_status_of_a_legacy_layout(tmp_path):
    client, _ = make_legacy(tmp_path)
    body = client.get("/api/storage").json()
    assert body["layout"] == "legacy" and body["root"] is None and body["suggestedRoot"] is None
    assert body["legacy"]["clips"] == str(tmp_path / "old" / "clips")
    assert body["resolved"]["fullVideos"]


def test_fresh_install_adopts_the_default_root_at_startup(tmp_path):
    path = tmp_path / "config.json"
    app = create_app(Config(paths=PathsConfig(temp=tmp_path / "tmp")), config_path=path)
    expected = tmp_path / "user" / "Videos" / "LumiaBriefingRoom"
    body = TestClient(app).get("/api/storage").json()
    assert body["layout"] == "new" and body["root"] == str(expected)
    assert load_config(path).paths.root == expected


def test_existing_user_keeps_legacy_layout_at_startup(tmp_path):
    cfg = Config(paths=PathsConfig(clips=tmp_path / "c", temp=tmp_path / "tmp"))
    assert adopt_default_root(cfg, tmp_path / "config.json").paths.root is None


def test_migrate_moves_videos_switches_config_and_keeps_clips_visible(tmp_path):
    client, config_path = make_legacy(tmp_path)
    store = tmp_path / "store"

    resp, status = run_move(client, {"root": str(store)})

    assert resp.status_code == 202 and status["state"] == "done" and status["moved"] == 3
    assert status["doneBytes"] == status["totalBytes"] > 0
    paths = load_config(config_path).paths
    assert paths.root == store and paths.clips is None and paths.vod_clips is None and paths.games is None
    assert (store / "clips" / "자동 보관" / "a.mp4").read_bytes() == b"VIDEO"
    assert (store / "full_video" / "steam_replay" / KEY / "full.mp4").exists()
    assert [c["id"] for c in client.get("/api/clips").json()] == ["a"]
    assert client.get("/api/clips/a/video").content == b"VIDEO"
    assert client.get("/api/games").json()["games"][0]["hasFullVideo"] is True
    assert client.get("/api/storage").json()["layout"] == "new"


def test_migrate_with_a_separate_full_video_folder(tmp_path):
    client, config_path = make_legacy(tmp_path)
    _, status = run_move(client, {"root": str(tmp_path / "store"), "fullVideos": str(tmp_path / "hdd")})
    assert status["state"] == "done"
    assert (tmp_path / "hdd" / "steam_replay" / KEY / "full.mp4").exists()
    assert load_config(config_path).paths.full_videos == tmp_path / "hdd"
    assert client.get("/api/storage").json()["fullVideos"] == str(tmp_path / "hdd")


def test_conflict_is_refused_and_config_is_unchanged(tmp_path):
    client, config_path = make_legacy(tmp_path)
    clash = tmp_path / "store" / "clips" / "자동 보관" / "a.mp4"
    clash.parent.mkdir(parents=True)
    clash.write_bytes(b"other")

    resp, _ = run_move(client, {"root": str(tmp_path / "store")})

    assert resp.status_code == 409
    assert load_config(config_path).paths.root is None
    assert (tmp_path / "old" / "clips" / "a.mp4").exists()


def test_a_root_is_required(tmp_path):
    client, _ = make_legacy(tmp_path)
    assert client.post("/api/storage/migrate", json={"root": " "}).status_code == 400


def test_migrate_is_refused_while_a_game_is_being_processed(tmp_path):
    client, _ = make_legacy(tmp_path)
    with activity.registry.track("reprocess", "게임 분석 중"):
        assert client.post("/api/storage/migrate", json={"root": str(tmp_path / "store")}).status_code == 409


def test_undo_restores_files_and_config(tmp_path):
    client, config_path = make_legacy(tmp_path)
    run_move(client, {"root": str(tmp_path / "store")})

    resp = client.post("/api/storage/undo")

    assert resp.status_code == 200 and resp.json()["restored"] is True
    assert (tmp_path / "old" / "clips" / "a.mp4").exists() and (tmp_path / "old" / "games" / KEY / "full.mp4").exists()
    paths = load_config(config_path).paths
    assert paths.root is None and paths.clips == tmp_path / "old" / "clips" and paths.games == tmp_path / "old" / "games"
    assert client.get("/api/storage").json()["layout"] == "legacy"
    assert client.post("/api/storage/undo").json()["restored"] is False


def test_moving_an_already_new_layout_to_another_root(tmp_path):
    client, config_path = make_legacy(tmp_path)
    run_move(client, {"root": str(tmp_path / "A")})
    (tmp_path / "A" / "clips" / "아야").mkdir()
    (tmp_path / "A" / "clips" / "자동 보관" / "a.mp4").rename(tmp_path / "A" / "clips" / "아야" / "a.mp4")

    _, status = run_move(client, {"root": str(tmp_path / "B")})

    assert status["state"] == "done"
    assert (tmp_path / "B" / "clips" / "아야" / "a.mp4").read_bytes() == b"VIDEO"
    assert client.get("/api/clips/a/video").content == b"VIDEO"


def test_status_flags_folders_on_the_same_disk_as_the_steam_recording(tmp_path, monkeypatch):
    from lumia_briefing_room.api import storage_routes

    recording = tmp_path / "steam video" / "video"
    recording.mkdir(parents=True)
    cfg = Config(paths=PathsConfig(root=tmp_path / "store", full_videos=tmp_path / "hdd" / "full", steam_recording=recording, temp=tmp_path / "tmp"))
    monkeypatch.setattr(storage_routes, "same_disk", lambda a, b: "hdd" in str(a) and b == recording)
    body = TestClient(create_app(cfg, config_path=tmp_path / "config.json")).get("/api/storage").json()
    assert body["recordingSameDisk"] == {"clips": False, "fullVideos": True}


def test_status_does_not_flag_anything_without_a_steam_recording_folder(tmp_path, monkeypatch):
    from lumia_briefing_room.api import storage_routes

    cfg = Config(paths=PathsConfig(root=tmp_path / "store", temp=tmp_path / "tmp"))
    monkeypatch.setattr(storage_routes, "resolve_recording_root", lambda configured: None)
    monkeypatch.setattr(storage_routes, "same_disk", lambda a, b: True)
    body = TestClient(create_app(cfg, config_path=tmp_path / "config.json")).get("/api/storage").json()
    assert body["recordingSameDisk"] == {"clips": False, "fullVideos": False}
