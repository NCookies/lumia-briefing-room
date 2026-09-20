import numpy as np

from lumia_briefing_room.detect.region import (
    build_region_template,
    load_region_templates,
    read_region,
    region_score,
    save_region_templates,
)

H, W = 30, 120


def _word(seed: int, width: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    score = np.zeros((H, W), np.float32)
    score[8:24, 4 : 4 + width] = (rng.random((16, width)) > 0.5).astype(np.float32)
    return score


def _to_rgb(score: np.ndarray, tint=(255, 255, 255), bg=20) -> np.ndarray:
    rgb = np.full((*score.shape, 3), bg, np.uint8)
    for c in range(3):
        rgb[..., c] = (bg + (np.array(tint)[c] - bg) * score).astype(np.uint8)
    return rgb


WORDS = {"묘지": _word(1, 40), "경찰서": _word(2, 64), "학교": _word(3, 40)}
TEMPLATES = {name: build_region_template([w]) for name, w in WORDS.items()}


def test_region_score_is_high_for_bright_text_regardless_of_hue():
    white = region_score(_to_rgb(WORDS["묘지"]))
    orange = region_score(_to_rgb(WORDS["묘지"], tint=(255, 160, 30)))

    assert white.max() > 0.9
    assert orange.max() > 0.5


def test_read_region_finds_the_matching_name():
    result = read_region(WORDS["경찰서"], TEMPLATES)

    assert result.name == "경찰서"
    assert result.confidence > 0.9


def test_read_region_tolerates_small_horizontal_shift():
    shifted = np.roll(WORDS["학교"], 2, axis=1)

    assert read_region(shifted, TEMPLATES).name == "학교"


def test_read_region_returns_none_for_unknown_text():
    unknown = _word(99, 52)

    assert read_region(unknown, TEMPLATES).name is None


def test_read_region_returns_none_for_empty_header():
    assert read_region(np.zeros((H, W), np.float32), TEMPLATES).name is None


def test_read_region_returns_none_without_templates():
    assert read_region(WORDS["묘지"], {}).name is None


def test_build_region_template_averages_samples_and_crops_to_text():
    a = _word(5, 40)
    b = np.clip(a + 0.05, 0, 1)

    template = build_region_template([a, b])

    assert template.shape[0] == H
    assert template.shape[1] < W
    assert read_region(a, {"x": template}).name == "x"


def test_region_templates_round_trip_through_npz(tmp_path):
    path = tmp_path / "regions.npz"

    save_region_templates(TEMPLATES, path)
    loaded = load_region_templates(path)

    assert set(loaded) == set(TEMPLATES)
    assert np.allclose(loaded["묘지"], TEMPLATES["묘지"])
