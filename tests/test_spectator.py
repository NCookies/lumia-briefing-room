import numpy as np

from lumia_briefing_room.detect.spectator import (
    hp_bar_visible,
    minimap_visible,
    read_spectating,
)


def _header(icon_fraction: float) -> np.ndarray:
    a = np.full((65, 135, 3), 20, np.uint8)
    n = int(a.shape[1] * icon_fraction)
    a[20:45, :n] = 210
    return a


def _strip(green_fraction: float) -> np.ndarray:
    a = np.full((140, 440, 3), 30, np.uint8)
    n = int(a.shape[0] * a.shape[1] * green_fraction)
    flat = a.reshape(-1, 3)
    flat[:n] = (90, 220, 40)
    return a


def test_minimap_visible_needs_bright_grey_icons():
    assert minimap_visible(_header(0.6)) is True
    assert minimap_visible(_header(0.0)) is False


def test_hp_bar_visible_needs_green_pixels():
    assert hp_bar_visible(_strip(0.05)) is True
    assert hp_bar_visible(_strip(0.0)) is False


def test_read_spectating_true_when_minimap_alive_but_character_ui_gone():
    assert read_spectating(_header(0.6), _strip(0.0)) is True


def test_read_spectating_false_when_character_ui_present():
    assert read_spectating(_header(0.6), _strip(0.05)) is False


def test_read_spectating_none_when_minimap_gone_such_as_blackout_or_lobby():
    assert read_spectating(_header(0.0), _strip(0.0)) is None


def test_read_spectating_falls_back_to_cobalt_header_when_default_header_is_empty():
    """코발트는 미니맵 헤더 아이콘도 배틀로얄과 다른 자리에 있다(실측, 코발트.mp4
    2026-09-29) - 기본 자리가 비어 있어도 코발트 자리에 아이콘이 보이면 로비/암전으로
    잘못 새면 안 된다."""
    assert read_spectating(_header(0.0), _strip(0.05), cobalt_header_rgb=_header(0.6)) is False
    assert read_spectating(_header(0.0), _strip(0.0), cobalt_header_rgb=_header(0.6)) is True


def test_read_spectating_stays_none_when_cobalt_header_also_empty():
    assert read_spectating(_header(0.0), _strip(0.0), cobalt_header_rgb=_header(0.0)) is None
