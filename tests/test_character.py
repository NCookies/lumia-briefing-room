import numpy as np

from lumia_briefing_room.detect.character import (
    clean_character_text,
    enhance_vertical_text,
    load_characters,
    resolve_character,
)

TABLE = {"MARKUS": "마커스", "MARTINA": "마르티나", "LENOX": "레녹스", "LENI": "레니", "LEON": "레온"}


def test_resolve_character_matches_exact_name():
    assert resolve_character("LEON", TABLE) == "레온"


def test_resolve_character_matches_unique_prefix_of_a_clipped_name():
    assert resolve_character("MARKU", TABLE) == "마커스"
    assert resolve_character("MARTIN", TABLE) == "마르티나"


def test_resolve_character_rejects_ambiguous_or_too_short_prefix():
    assert resolve_character("LEN", TABLE) is None
    assert resolve_character("MAR", TABLE) is None
    assert resolve_character("ZZZZ", TABLE) is None
    assert resolve_character(None, TABLE) is None


def test_clean_character_text_keeps_only_uppercase_latin_letters():
    assert clean_character_text("MARK U") == "MARKU"
    assert clean_character_text(" marti-na1 ") == "MARTINA"
    assert clean_character_text("한글") is None
    assert clean_character_text("AB") is None


def test_enhance_vertical_text_stretches_contrast_and_rotates_upright():
    crop = np.zeros((40, 10, 3), dtype=np.uint8)
    crop[:, 3:6] = 30
    crop[:, :3] = 20

    out = enhance_vertical_text(crop)

    assert out.shape[0] == 10 * 2 and out.shape[1] == 40 * 2
    assert out.dtype == np.uint8 and out.max() == 255


def test_load_characters_reads_upper_cased_english_to_korean(tmp_path):
    path = tmp_path / "c.json"
    path.write_text('{"markus": "마커스"}', encoding="utf-8")

    assert load_characters(path) == {"MARKUS": "마커스"}
