from fastapi.testclient import TestClient

from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.appmode import resolve_mode
from lumia_briefing_room.config import AppConfig, Config, dataclass_from_camel_dict, dataclass_to_camel_dict


def test_auto_follows_frozen_flag():
    assert resolve_mode("auto", frozen=True) == "release"
    assert resolve_mode("auto", frozen=False) == "dev"


def test_explicit_setting_overrides_frozen():
    assert resolve_mode("dev", frozen=True) == "dev"
    assert resolve_mode("release", frozen=False) == "release"


def test_unknown_setting_falls_back_to_auto():
    assert resolve_mode("nonsense", frozen=True) == "release"
    assert resolve_mode("", frozen=False) == "dev"
    assert resolve_mode(None, frozen=False) == "dev"


def test_config_default_is_auto_and_roundtrips():
    cfg = Config()
    assert cfg.app.mode == "auto"
    data = dataclass_to_camel_dict(cfg)
    assert data["app"] == {"mode": "auto"}
    back = dataclass_from_camel_dict(Config, {"app": {"mode": "release"}})
    assert back.app == AppConfig(mode="release")


def test_app_info_reports_mode_from_config(monkeypatch):
    dev = TestClient(create_app(Config())).get("/api/app-info").json()
    assert dev["mode"] == "dev"

    forced = TestClient(create_app(Config(app=AppConfig(mode="release")))).get("/api/app-info").json()
    assert forced["mode"] == "release"


def test_app_info_mode_follows_live_config_change():
    client = TestClient(create_app(Config()))
    client.put("/api/config", json={"app": {"mode": "release"}})
    assert client.get("/api/app-info").json()["mode"] == "release"
