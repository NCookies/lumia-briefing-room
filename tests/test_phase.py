import numpy as np

from lumia_briefing_room.detect.phase import V_LO, read_cobalt_phase
from lumia_briefing_room.detect.region import build_region_template, region_score

H, W = 17, 19


def _score(rgb: np.ndarray) -> np.ndarray:
    return region_score(rgb, v_lo=V_LO)


def _text(seed: int) -> np.ndarray:
    """§10-1 실측: `Phase N` 숫자는 옅은 주황 글자다(흰 글자가 아니고, 밝기도 지역 경고색보다 낮다)."""
    rng = np.random.default_rng(seed)
    rgb = np.full((H, W, 3), 30, np.uint8)
    ink = rng.random((10, 12)) > 0.5
    rgb[4:14, 4:16][ink] = (190, 110, 50)
    return rgb


TEMPLATES = {str(d): build_region_template([_score(_text(d))]) for d in (0, 1, 2, 3)}


def test_reads_the_phase_number_as_an_int():
    assert read_cobalt_phase(_text(0), TEMPLATES) == 0
    assert read_cobalt_phase(_text(3), TEMPLATES) == 3


def test_returns_none_for_a_digit_it_has_never_seen():
    assert read_cobalt_phase(_text(99), TEMPLATES) is None


def test_returns_none_without_templates_or_for_a_blank_header():
    assert read_cobalt_phase(_text(1), {}) is None
    assert read_cobalt_phase(np.full((H, W, 3), 30, np.uint8), TEMPLATES) is None


def test_ignores_template_names_that_are_not_numbers():
    assert read_cobalt_phase(_text(2), {"묘지": build_region_template([_score(_text(2))])}) is None


def test_the_same_phase_reads_the_same_on_different_backgrounds():
    """전투 준비(Phase 0)와 교전 중 배경색이 다르지만 같은 주황 숫자여야 한다."""
    rng = np.random.default_rng(7)
    ink = rng.random((10, 12)) > 0.5

    def render(bg):
        rgb = np.full((H, W, 3), bg, np.uint8)
        rgb[4:14, 4:16][ink] = (190, 110, 50)
        return rgb

    templates = {"1": build_region_template([_score(render((25, 30, 45)))])}

    assert read_cobalt_phase(render((25, 30, 45)), templates) == 1
    assert read_cobalt_phase(render((60, 20, 60)), templates) == 1
