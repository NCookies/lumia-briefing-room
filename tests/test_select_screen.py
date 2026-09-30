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


def _mode_crop(mask):
    crop = np.full(mask.shape + (3,), (20, 30, 45), np.uint8)
    crop[mask] = (140, 230, 255)
    return crop


def test_practice_text_is_recognised_and_normal_game_is_not():
    from lumia_briefing_room.detect.select_screen import _practice_mask, read_practice_mode

    ref = _practice_mask()
    assert read_practice_mode(_mode_crop(ref)) is True
    normal = np.zeros_like(ref)
    normal[6:16, 5:170] = True
    assert read_practice_mode(_mode_crop(normal)) is False
    assert read_practice_mode(_mode_crop(np.zeros_like(ref))) is False


def test_practice_reading_tolerates_a_scaled_crop():
    from lumia_briefing_room.detect.select_screen import _practice_mask, read_practice_mode

    ref = _practice_mask()
    assert read_practice_mode(_mode_crop(np.repeat(np.repeat(ref, 2, 0), 2, 1))) is True
