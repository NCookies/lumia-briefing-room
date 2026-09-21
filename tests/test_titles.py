from lumia_briefing_room.pipeline.orchestrator import default_title
from lumia_briefing_room.pipeline.titles import characters_of, is_auto_title, retitle


def meta(**kw):
    base = {
        "title": "5일차 낮 경찰서 교전", "dayNight": "day", "region": "경찰서", "gameDay": 5,
        "myCharacter": None, "teamCharacters": [],
    }
    base.update(kw)
    return base


def test_default_title_appends_known_characters_after_a_dot():
    assert default_title("day", "경찰서", 5, ["마커스", "루치아"]) == "5일차 낮 경찰서 교전 · 마커스, 루치아"
    assert default_title("day", "경찰서", 5, []) == "5일차 낮 경찰서 교전"
    assert default_title("day", "경찰서", 5, None) == "5일차 낮 경찰서 교전"


def test_characters_of_puts_my_character_first_and_skips_blanks():
    assert characters_of(meta(myCharacter="마커스", teamCharacters=["루치아", "", None])) == ["마커스", "루치아"]
    assert characters_of(meta()) == []


def test_is_auto_title_recognizes_generated_titles_with_or_without_characters():
    assert is_auto_title(meta())
    assert is_auto_title(meta(title="5일차 낮 경찰서 교전 · 마커스, 루치아"))
    assert is_auto_title(meta(title="낮 경찰서 교전"))
    assert not is_auto_title(meta(title="내가 붙인 제목"))
    assert not is_auto_title(meta(title="5일차 낮 경찰서 교전 멋진 킬"))


def test_retitle_adds_characters_to_an_auto_title():
    new = retitle(meta(myCharacter="마커스", teamCharacters=["루치아"]))

    assert new["title"] == "5일차 낮 경찰서 교전 · 마커스, 루치아"


def test_retitle_replaces_an_old_character_suffix_and_never_touches_custom_titles():
    old = meta(title="5일차 낮 경찰서 교전 · 마커스", myCharacter="마커스", teamCharacters=["루치아"])
    custom = meta(title="내가 붙인 제목", myCharacter="마커스")

    assert retitle(old)["title"] == "5일차 낮 경찰서 교전 · 마커스, 루치아"
    assert retitle(custom) is custom
