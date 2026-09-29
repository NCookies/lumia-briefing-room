import numpy as np

from lumia_briefing_room.detect.select_screen import read_select_screen


def _timer(cyan_frac: float) -> np.ndarray:
    crop = np.full((65, 110, 3), (10, 30, 60), np.uint8)
    n = int(crop.shape[0] * crop.shape[1] * cyan_frac)
    crop.reshape(-1, 3)[:n] = (0, 210, 255)
    return crop


def _title(bright_frac: float, base: int = 45) -> np.ndarray:
    crop = np.full((34, 230, 3), base, np.uint8)
    n = int(crop.shape[0] * crop.shape[1] * bright_frac)
    crop.reshape(-1, 3)[:n] = (150, 150, 150)
    return crop


def test_selection_header_is_detected():
    assert read_select_screen(_timer(0.18), _title(0.12)) is True


def test_timer_only_is_not_enough():
    assert read_select_screen(_timer(0.18), _title(0.0)) is False


def test_title_only_is_not_enough():
    assert read_select_screen(_timer(0.0), _title(0.12)) is False


def test_bright_scene_in_title_area_is_rejected():
    assert read_select_screen(_timer(0.18), _title(0.9, base=120)) is False
