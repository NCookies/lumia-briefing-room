import uuid

import pytest

from lumia_briefing_room import autostart

pytestmark = pytest.mark.skipif(not autostart.is_supported(), reason="Windows 전용 기능이다")


@pytest.fixture
def app_name():
    name = f"LumiaBriefingRoomTest_{uuid.uuid4().hex[:8]}"
    yield name
    autostart.disable(app_name=name)  # 테스트가 실패해도 레지스트리에 남기지 않는다


def test_is_enabled_false_initially(app_name):
    assert autostart.is_enabled(app_name=app_name) is False


def test_enable_then_is_enabled_true(app_name):
    autostart.enable("C:\\fake\\app.exe --minimized", app_name=app_name)
    assert autostart.is_enabled(app_name=app_name) is True


def test_get_command_returns_what_was_set(app_name):
    autostart.enable("C:\\fake\\app.exe --minimized", app_name=app_name)
    assert autostart.get_command(app_name=app_name) == "C:\\fake\\app.exe --minimized"


def test_get_command_none_when_not_set(app_name):
    assert autostart.get_command(app_name=app_name) is None


def test_disable_removes_entry(app_name):
    autostart.enable("C:\\fake\\app.exe", app_name=app_name)
    autostart.disable(app_name=app_name)
    assert autostart.is_enabled(app_name=app_name) is False


def test_disable_when_not_enabled_does_not_raise(app_name):
    autostart.disable(app_name=app_name)  # 존재하지 않아도 조용히 넘어간다


def test_enable_overwrites_existing_command(app_name):
    autostart.enable("C:\\old.exe", app_name=app_name)
    autostart.enable("C:\\new.exe", app_name=app_name)
    assert autostart.get_command(app_name=app_name) == "C:\\new.exe"


def test_command_for_a_frozen_build_is_the_exe_alone():
    assert autostart.build_command(frozen=True, executable="C:/Apps/Lumia/Lumia.exe") == '"C:/Apps/Lumia/Lumia.exe"'


def test_command_in_the_source_tree_runs_the_module():
    cmd = autostart.build_command(frozen=False, executable="C:/venv/python.exe")
    assert cmd == '"C:/venv/python.exe" -m lumia_briefing_room.cli.app'


def test_current_command_uses_this_process():
    import sys

    assert sys.executable in autostart.current_command()


@pytest.mark.skipif(not autostart.is_supported(), reason="Windows 전용 기능이다")
def test_apply_setting_writes_and_removes_the_registry_value():
    from lumia_briefing_room.config import Config, UiConfig

    name = f"LumiaBriefingRoomTest_{uuid.uuid4().hex[:8]}"
    try:
        autostart.apply_setting(Config(ui=UiConfig(auto_start=True)), app_name=name)
        assert autostart.get_command(app_name=name) == autostart.current_command()

        autostart.apply_setting(Config(ui=UiConfig(auto_start=False)), app_name=name)
        assert autostart.is_enabled(app_name=name) is False
    finally:
        autostart.disable(app_name=name)
