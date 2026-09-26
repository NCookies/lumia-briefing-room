from pathlib import Path

import pytest

from lumia_briefing_room import autostart, paths
from lumia_briefing_room.config import Config, PathsConfig, resolve_paths


def test_no_profile_keeps_the_original_folder_names(monkeypatch):
    monkeypatch.delenv(paths.PROFILE_ENV, raising=False)
    assert paths.profile() == "" and paths.app_folder_name() == "LumiaBriefingRoom"


@pytest.mark.parametrize("raw,expected", [("dev", "dev"), (" Side_1 ", "Side_1"), ("../x", ""), ("a b", ""), ("", ""), ("x" * 40, "")])
def test_profile_accepts_only_short_safe_names(monkeypatch, raw, expected):
    monkeypatch.setenv(paths.PROFILE_ENV, raw)
    assert paths.profile() == expected


def test_profile_changes_every_per_user_location(monkeypatch, tmp_path):
    from lumia_briefing_room import logsetup, updater
    from lumia_briefing_room.telemetry import outbox, runtime_stats, state

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
    monkeypatch.setenv(paths.PROFILE_ENV, "dev")
    from lumia_briefing_room import config

    found = [
        config.default_config_path(),
        logsetup.default_log_path(),
        outbox.default_outbox_path(),
        outbox.default_recent_path(),
        runtime_stats.default_stats_path(),
        state.default_state_path(),
        updater.default_state_path(),
        updater.default_download_dir(),
    ]
    for p in found:
        assert "LumiaBriefingRoom-dev" in Path(p).parts, p
        assert "LumiaBriefingRoom" not in Path(p).parts, p


def test_clip_and_temp_defaults_follow_the_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
    monkeypatch.setenv(paths.PROFILE_ENV, "dev")
    resolved = resolve_paths(PathsConfig())
    assert resolved.clips == tmp_path / "user" / "Videos" / "LumiaBriefingRoom-dev" / "clips"
    assert resolved.vod_clips == tmp_path / "user" / "Videos" / "LumiaBriefingRoom-dev" / "vod"
    assert resolved.temp == tmp_path / "local" / "Temp" / "LumiaBriefingRoom-dev"
    monkeypatch.delenv(paths.PROFILE_ENV)
    assert resolve_paths(PathsConfig()).clips == tmp_path / "user" / "Videos" / "LumiaBriefingRoom" / "clips"


def test_single_instance_name_follows_the_profile(monkeypatch):
    from lumia_briefing_room.single_instance import default_name

    monkeypatch.delenv(paths.PROFILE_ENV, raising=False)
    assert default_name() == "LumiaBriefingRoom.SingleInstance"
    monkeypatch.setenv(paths.PROFILE_ENV, "dev")
    assert default_name() == "LumiaBriefingRoom-dev.SingleInstance"


def test_a_profile_never_touches_the_autostart_registry(monkeypatch):
    calls = []
    monkeypatch.setattr(autostart, "is_supported", lambda: True)
    monkeypatch.setattr(autostart, "enable", lambda *a, **k: calls.append("enable"))
    monkeypatch.setattr(autostart, "disable", lambda *a, **k: calls.append("disable"))
    monkeypatch.setenv(paths.PROFILE_ENV, "dev")
    autostart.apply_setting(Config())
    assert calls == []
    monkeypatch.delenv(paths.PROFILE_ENV)
    autostart.apply_setting(Config())
    assert calls
