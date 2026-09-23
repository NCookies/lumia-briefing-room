from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room import autostart
from lumia_briefing_room.api import app as app_module
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig, UiConfig, load_config


@pytest.fixture
def applied(monkeypatch):
    calls = []
    monkeypatch.setattr(app_module.autostart, "apply_setting", lambda cfg: calls.append(cfg.ui.auto_start))
    return calls


@pytest.fixture
def client(tmp_path):
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp"))
    app = create_app(cfg, config_path=tmp_path / "config.json")
    app.state.config_path_for_test = tmp_path / "config.json"
    return TestClient(app)


def test_turning_autostart_off_is_applied_to_the_registry(client, applied):
    resp = client.put("/api/config", json={"ui": {"autoStart": False}})

    assert resp.status_code == 200
    assert resp.json()["ui"]["autoStart"] is False
    assert applied == [False]


def test_turning_autostart_on_is_applied_to_the_registry(client, applied):
    client.put("/api/config", json={"ui": {"autoStart": False}})
    applied.clear()

    client.put("/api/config", json={"ui": {"autoStart": True}})

    assert applied == [True]


def test_the_choice_is_saved_to_the_config_file(client, applied):
    client.put("/api/config", json={"ui": {"autoStart": False}})
    assert load_config(client.app.state.config_path_for_test).ui.auto_start is False


def test_unrelated_settings_do_not_touch_the_registry(client, applied):
    client.put("/api/config", json={"player": {"nickname": "루미아"}})
    client.put("/api/config", json={"ui": {"confirmDelete": False}})

    assert applied == []


def test_current_state_is_reported_so_the_screen_can_show_it(client):
    body = client.get("/api/config").json()
    assert body["ui"]["autoStart"] is True


@pytest.mark.skipif(not autostart.is_supported(), reason="Windows 전용 기능이다")
def test_the_registry_really_changes_end_to_end(tmp_path: Path, monkeypatch):
    import uuid

    name = f"LumiaBriefingRoomTest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(app_module.autostart, "APP_NAME", name)
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp"), ui=UiConfig(auto_start=False))
    client = TestClient(create_app(cfg, config_path=tmp_path / "config.json"))
    try:
        client.put("/api/config", json={"ui": {"autoStart": True}})
        assert autostart.get_command(app_name=name) == autostart.current_command()

        client.put("/api/config", json={"ui": {"autoStart": False}})
        assert autostart.is_enabled(app_name=name) is False
    finally:
        autostart.disable(app_name=name)
