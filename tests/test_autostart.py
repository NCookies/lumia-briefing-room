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
