import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from backfill_result import apply_match_result, group_by_match  # noqa: E402

from lumia_briefing_room.detect.result import ResultScreen

RESULT = ResultScreen(
    placement=4, total=7, match_type="rank", match_label="랭크", outcome="실험 종료", nickname="나"
)


def test_apply_match_result_adds_camel_dict_without_touching_other_fields():
    meta = {"title": "낮 교전", "userLabel": "pvp"}

    new = apply_match_result(meta, RESULT)

    assert new["matchResult"]["placement"] == 4
    assert new["matchResult"]["matchType"] == "rank"
    assert new["title"] == "낮 교전" and new["userLabel"] == "pvp"
    assert "matchResult" not in meta


def test_apply_match_result_fills_my_character_only_when_empty():
    with_char = ResultScreen(
        placement=1, total=8, match_type="rank", match_label="랭크", outcome="최종 생존",
        nickname="나", character="마커스", character_raw="MARKU",
    )

    assert apply_match_result({"myCharacter": None}, with_char)["myCharacter"] == "마커스"
    assert apply_match_result({"myCharacter": "직접"}, with_char)["myCharacter"] == "직접"


def test_group_by_match_groups_clips_of_one_game_and_tracks_last_segment():
    metas = {
        "a": {"sessionDir": "s1", "matchStartUtc": "t1", "segmentEnd": 10},
        "b": {"sessionDir": "s1", "matchStartUtc": "t1", "segmentEnd": 30},
        "c": {"sessionDir": "s1", "matchStartUtc": "t2", "segmentEnd": 50},
    }

    groups = group_by_match(metas)

    assert set(groups[("s1", "t1")].ids) == {"a", "b"}
    assert groups[("s1", "t1")].last_segment == 30
    assert groups[("s1", "t2")].last_segment == 50


def test_apply_match_result_fills_team_characters_but_titles_only_with_my_character():
    result = ResultScreen(
        placement=1, total=8, match_type="rank", match_label="랭크", outcome="최종 생존", nickname="나",
        character="마커스", character_raw="MARKU",
        teammates=[{"nickname": "a", "character": "루치아"}, {"nickname": "b", "character": None}],
    )
    meta = {"title": "5일차 낮 경찰서 교전", "dayNight": "day", "region": "경찰서", "gameDay": 5, "myCharacter": None}

    new = apply_match_result(meta, result)

    assert new["teamCharacters"] == ["루치아"]
    assert new["title"] == "5일차 낮 경찰서 교전 · 마커스"
    assert new["matchResult"]["teammates"] == result.teammates


def test_apply_match_result_keeps_a_custom_title():
    result = ResultScreen(
        placement=1, total=8, match_type="rank", match_label="랭크", outcome="최종 생존", nickname="나",
        character="마커스",
    )

    assert apply_match_result({"title": "내가 붙인 제목", "dayNight": "day"}, result)["title"] == "내가 붙인 제목"
