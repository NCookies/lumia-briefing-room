import pytest

from lumia_briefing_room.pipeline.label_note import LABEL_NOTE_MAX, normalize_label_note


def test_none_and_blank_become_none():
    assert normalize_label_note(None) is None
    assert normalize_label_note("") is None
    assert normalize_label_note("  \n ") is None


def test_surrounding_whitespace_is_trimmed():
    assert normalize_label_note("  궁 쓰고 도망  ") == "궁 쓰고 도망"


def test_over_limit_is_cut_to_max():
    assert normalize_label_note("가" * (LABEL_NOTE_MAX + 50)) == "가" * LABEL_NOTE_MAX


def test_limit_is_500():
    assert LABEL_NOTE_MAX == 500


def test_non_string_is_rejected():
    with pytest.raises(ValueError):
        normalize_label_note(123)
