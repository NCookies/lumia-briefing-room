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


def _card(bar=(30, 140, 255), below=(70, 75, 85), bar_rows=6, rows=15, width=240):
    crop = np.full((rows, width, 3), below, np.uint8)
    crop[:bar_rows] = bar
    return crop


def test_team_card_bars_mark_a_selection_screen_even_when_the_header_is_covered():
    from lumia_briefing_room.detect.select_screen import read_select_cards

    assert read_select_cards([_card(), _card(bar=(60, 200, 40)), _card(bar=(240, 200, 20))]) is True


def test_card_bars_scale_with_the_crop():
    from lumia_briefing_room.detect.select_screen import read_select_cards

    assert read_select_cards([_card(bar_rows=8, rows=20, width=320)] * 3) is True


def test_one_missing_bar_is_not_a_selection_screen():
    from lumia_briefing_room.detect.select_screen import read_select_cards

    assert read_select_cards([_card(), _card(bar=(70, 75, 85)), _card()]) is False


def test_a_colorful_area_is_not_a_thin_bar():
    from lumia_briefing_room.detect.select_screen import read_select_cards

    assert read_select_cards([_card(below=(30, 140, 255))] * 3) is False


def test_grey_bars_are_not_team_colors():
    from lumia_briefing_room.detect.select_screen import read_select_cards

    assert read_select_cards([_card(bar=(200, 200, 200))] * 3) is False


def test_selection_screen_on_a_1080p_frame_by_header_or_by_card_bars():
    from lumia_briefing_room.detect.select_screen import is_select_screen
    from lumia_briefing_room.profiles.models import ResolutionProfile

    profile = ResolutionProfile.for_resolution(1920, 1080)
    frame = np.full((1080, 1920, 3), 20, np.uint8)
    assert is_select_screen(frame, profile) is False

    for i in (1, 2, 3):
        roi = profile.rois[f"select_card{i}"]
        frame[roi.y0 : roi.y1, roi.x0 : roi.x1] = _card(rows=roi.y1 - roi.y0, width=roi.x1 - roi.x0)
    assert is_select_screen(frame, profile) is True


def test_2560_profile_without_card_rois_still_uses_the_header_only():
    from lumia_briefing_room.detect.select_screen import is_select_screen
    from lumia_briefing_room.profiles.models import ResolutionProfile

    profile = ResolutionProfile.for_resolution(2560, 1440)
    assert is_select_screen(np.full((1440, 2560, 3), 20, np.uint8), profile) is False
