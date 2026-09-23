import sys
import uuid

import pytest

from lumia_briefing_room import autostart
from lumia_briefing_room.cli.app import apply_autostart_setting, autostart_command, build_autostart_command
from lumia_briefing_room.config import Config, UiConfig

requires_windows = pytest.mark.skipif(not autostart.is_supported(), reason="Windows 전용 기능이다")


def test_build_autostart_command_dev_runs_module_with_python():
    cmd = build_autostart_command(frozen=False, executable="C:/venv/python.exe")
    assert cmd == '"C:/venv/python.exe" -m lumia_briefing_room.cli.app'


def test_build_autostart_command_frozen_runs_exe_only():
    cmd = build_autostart_command(frozen=True, executable="C:/Apps/LumiaBriefingRoom/LumiaBriefingRoom.exe")
    assert cmd == '"C:/Apps/LumiaBriefingRoom/LumiaBriefingRoom.exe"'
    assert "-m" not in cmd


def test_autostart_command_uses_current_process():
    cmd = autostart_command()
    assert sys.executable in cmd
    assert "lumia_briefing_room.cli.app" in cmd


@pytest.fixture
def app_name():
    name = f"LumiaBriefingRoomTest_{uuid.uuid4().hex[:8]}"
    yield name
    autostart.disable(app_name=name)


@requires_windows
def test_apply_autostart_setting_enables_when_configured(app_name):
    cfg = Config(ui=UiConfig(auto_start=True))
    apply_autostart_setting(cfg, app_name=app_name)
    assert autostart.is_enabled(app_name=app_name) is True


@requires_windows
def test_apply_autostart_setting_disables_when_not_configured(app_name):
    autostart.enable("dummy", app_name=app_name)
    cfg = Config(ui=UiConfig(auto_start=False))
    apply_autostart_setting(cfg, app_name=app_name)
    assert autostart.is_enabled(app_name=app_name) is False


@requires_windows
def test_apply_autostart_setting_overwrites_stale_command(app_name):
    autostart.enable('"C:/old/python.exe" -m lumia_briefing_room.cli.app', app_name=app_name)
    apply_autostart_setting(Config(ui=UiConfig(auto_start=True)), app_name=app_name)
    assert autostart.get_command(app_name=app_name) == autostart_command()
