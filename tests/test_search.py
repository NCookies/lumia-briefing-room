from lumia_briefing_room.api.search import first_match, matches, normalize


def test_normalize_ignores_case_and_all_whitespace():
    assert normalize(" Hello  World\t") == "helloworld"
    assert normalize("가 나\n다") == "가나다"


def test_matches_is_a_substring_test_on_normalized_text():
    assert matches("마지막 교전", "교 전")
    assert matches("FINAL Fight", "al fi")
    assert not matches("마지막 교전", "우승")


def test_empty_needle_matches_nothing_because_it_is_not_a_search():
    assert not matches("아무거나", "   ")


def test_first_match_returns_the_first_field_in_priority_order():
    fields = [("게임 제목", "첫 우승"), ("후보", "첫 교전"), ("메모", "첫 느낌")]
    assert first_match("첫", fields) == {"where": "게임 제목", "text": "첫 우승"}
    assert first_match("교전", fields) == {"where": "후보", "text": "첫 교전"}
    assert first_match("없음", fields) is None


def test_first_match_skips_empty_fields():
    assert first_match("a", [("게임 제목", None), ("메모", "")]) is None
