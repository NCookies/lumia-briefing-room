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
