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


def test_selftest_command_writes_a_report_and_can_stay_quiet(tmp_path, monkeypatch):
    import argparse

    from lumia_briefing_room import selftest as selftest_module
    from lumia_briefing_room.cli import app as app_module

    opened = []
    monkeypatch.setattr(app_module, "default_log_path", lambda: tmp_path / "logs" / "app.log")
    monkeypatch.setattr(app_module.os, "startfile", lambda path: opened.append(path), raising=False)
    monkeypatch.setattr(app_module.startup, "console_logging_wanted", lambda: False)
    monkeypatch.setattr(
        selftest_module, "run_all", lambda: ([selftest_module.Check("가짜", True, "좋다")], True)
    )

    assert app_module.run_selftest_command(argparse.Namespace(quiet=True)) is True

    report = (tmp_path / "logs" / "selftest.txt").read_text(encoding="utf-8")
    assert "가짜" in report and "모두 통과" in report
    assert opened == []


def test_selftest_command_opens_the_report_when_there_is_no_console(tmp_path, monkeypatch):
    import argparse

    from lumia_briefing_room import selftest as selftest_module
    from lumia_briefing_room.cli import app as app_module

    opened = []
    monkeypatch.setattr(app_module, "default_log_path", lambda: tmp_path / "logs" / "app.log")
    monkeypatch.setattr(app_module.os, "startfile", lambda path: opened.append(path), raising=False)
    monkeypatch.setattr(app_module.startup, "console_logging_wanted", lambda: False)
    monkeypatch.setattr(
        selftest_module, "run_all", lambda: ([selftest_module.Check("가짜", False, "나쁘다")], False)
    )

    assert app_module.run_selftest_command(argparse.Namespace(quiet=False)) is False
    assert opened == [tmp_path / "logs" / "selftest.txt"]
