from pathlib import Path

from tests.test_legacy_games import KEY, _setup


def test_rebuild_button_endpoints(tmp_path, monkeypatch):
    import time

    from fastapi.testclient import TestClient

    from lumia_briefing_room.api import game_routes
    from lumia_briefing_room.api.app import create_app
    from lumia_briefing_room.config import Config, PathsConfig

    clips, games = _setup(tmp_path)
    cfg = Config(paths=PathsConfig(clips=clips, temp=tmp_path / "tmp", games=games))
    client = TestClient(create_app(cfg, config_path=tmp_path / "config.json"))
    client.get("/api/games")
    ran = []
    monkeypatch.setattr(game_routes, "resolve_recording_root", lambda p: tmp_path)
    monkeypatch.setattr(game_routes, "discover_ffmpeg", lambda: Path("ffmpeg"))
    monkeypatch.setattr(game_routes, "can_rebuild", lambda game, gdir, root: True)
    monkeypatch.setattr(game_routes, "rebuild_full_video", lambda **kw: ran.append(kw["key"]))

    assert client.get(f"/api/games/{KEY}").json()["canRebuildFullVideo"] is True
    assert client.post(f"/api/games/{KEY}/full-video").status_code == 202
    for _ in range(50):
        state = client.get(f"/api/games/{KEY}/full-video/status").json()["state"]
        if state != "running":
            break
        time.sleep(0.05)

    assert state == "done" and ran == [KEY]
    monkeypatch.setattr(game_routes, "can_rebuild", lambda game, gdir, root: False)
    assert client.post(f"/api/games/{KEY}/full-video").status_code == 409


def test_list_marks_which_legacy_games_can_be_rebuilt(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from lumia_briefing_room.api import game_routes
    from lumia_briefing_room.api.app import create_app
    from lumia_briefing_room.config import Config, PathsConfig

    clips, games = _setup(tmp_path)
    cfg = Config(paths=PathsConfig(clips=clips, temp=tmp_path / "tmp", games=games))
    client = TestClient(create_app(cfg, config_path=tmp_path / "config.json"))
    monkeypatch.setattr(game_routes, "resolve_recording_root", lambda p: tmp_path)
    monkeypatch.setattr(game_routes, "can_rebuild", lambda game, gdir, root: True)
    listed = client.get("/api/games").json()["games"]
    assert [g["canRebuildFullVideo"] for g in listed] == [True]
    monkeypatch.setattr(game_routes, "can_rebuild", lambda game, gdir, root: False)
    assert client.get("/api/games").json()["games"][0]["canRebuildFullVideo"] is False
