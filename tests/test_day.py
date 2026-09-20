import numpy as np

from lumia_briefing_room.detect.day import read_game_day, white_score
from lumia_briefing_room.detect.region import build_region_template

H, W = 26, 60


def _text(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    rgb = np.full((H, W, 3), 25, np.uint8)
    ink = rng.random((14, 40)) > 0.5
    rgb[6:20, 6:46][ink] = 255
    return rgb


TEMPLATES = {str(d): build_region_template([white_score(_text(d))]) for d in (1, 2, 3, 4)}


def test_reads_the_day_number_as_an_int():
    assert read_game_day(_text(4), TEMPLATES) == 4
    assert read_game_day(_text(2), TEMPLATES) == 2


def test_returns_none_for_text_it_has_never_seen():
    assert read_game_day(_text(99), TEMPLATES) is None


def test_returns_none_without_templates_or_for_a_blank_header():
    assert read_game_day(_text(1), {}) is None
    assert read_game_day(np.full((H, W, 3), 25, np.uint8), TEMPLATES) is None


def test_ignores_template_names_that_are_not_numbers():
    assert read_game_day(_text(7), {"묘지": build_region_template([white_score(_text(7))])}) is None


def test_white_score_ignores_saturated_backgrounds_but_keeps_white_text():
    bg_red = np.full((4, 4, 3), (170, 20, 20), np.uint8)
    bg_orange = np.full((4, 4, 3), (200, 120, 30), np.uint8)
    cream = np.full((4, 4, 3), (245, 235, 205), np.uint8)

    assert white_score(bg_red).max() == 0.0
    assert white_score(bg_orange).max() == 0.0
    assert white_score(cream).min() > 0.4


def test_the_same_digit_reads_the_same_on_a_red_and_on_a_dark_background():
    rng = np.random.default_rng(3)
    ink = rng.random((14, 11)) > 0.5

    def render(bg):
        rgb = np.full((26, 15, 3), bg, np.uint8)
        rgb[6:20, 2:13][ink] = (245, 240, 220)
        return rgb

    templates = {"6": build_region_template([white_score(render((20, 25, 35)))])}

    assert read_game_day(render((20, 25, 35)), templates) == 6
    assert read_game_day(render((175, 15, 15)), templates) == 6
