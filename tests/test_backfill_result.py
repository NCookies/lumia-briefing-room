import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from backfill_result import apply_match_result, group_by_match, is_locked  # noqa: E402

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


def test_is_locked_when_any_clip_in_the_game_was_manually_corrected():
    from backfill_result import MatchGroup

    metas = {
        "a": {"matchResultSource": None},
        "b": {"matchResultSource": "manual"},
    }
    assert is_locked(metas, MatchGroup(ids=["a", "b"])) is True
    assert is_locked(metas, MatchGroup(ids=["a"])) is False


def test_apply_match_result_keeps_a_custom_title():
    result = ResultScreen(
        placement=1, total=8, match_type="rank", match_label="랭크", outcome="최종 생존", nickname="나",
    )

    assert apply_match_result({"title": "내가 붙인 제목", "dayNight": "day"}, result)["title"] == "내가 붙인 제목"
