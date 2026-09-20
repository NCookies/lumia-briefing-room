import sys
import uuid

import pytest

from lumia_briefing_room import autostart
from lumia_briefing_room.cli.app import apply_autostart_setting, autostart_command
from lumia_briefing_room.config import Config, UiConfig

pytestmark = pytest.mark.skipif(not autostart.is_supported(), reason="Windows 전용 기능이다")


def test_autostart_command_includes_python_executable():
    cmd = autostart_command()
    assert sys.executable in cmd
    assert "lumia_briefing_room.cli.app" in cmd


@pytest.fixture
def app_name():
    name = f"LumiaBriefingRoomTest_{uuid.uuid4().hex[:8]}"
    yield name
    autostart.disable(app_name=name)


def test_apply_autostart_setting_enables_when_configured(app_name):
    cfg = Config(ui=UiConfig(auto_start=True))
    apply_autostart_setting(cfg, app_name=app_name)
    assert autostart.is_enabled(app_name=app_name) is True


def test_apply_autostart_setting_disables_when_not_configured(app_name):
    autostart.enable("dummy", app_name=app_name)
    cfg = Config(ui=UiConfig(auto_start=False))
    apply_autostart_setting(cfg, app_name=app_name)
    assert autostart.is_enabled(app_name=app_name) is False
