import json

import pytest

from lumia_briefing_room.pipeline.game_edit import (
    GameEditError,
    carry_user_fields,
    lock_result,
    normalize_title,
    sync_clip_results,
    validate_result_edit,
)


def test_title_is_trimmed_and_empty_means_no_title():
    assert normalize_title("  첫 우승  ") == "첫 우승"
    assert normalize_title("   ") is None
    assert normalize_title(None) is None


def test_title_must_be_text_and_not_too_long():
    with pytest.raises(GameEditError):
        normalize_title(123)
    with pytest.raises(GameEditError):
        normalize_title("가" * 61)


def test_result_edit_accepts_known_fields_only():
    assert validate_result_edit({"placement": 3, "matchType": "rank", "tk": 12, "kills": 4, "assists": 0}, cobalt=False) == {
        "placement": 3, "matchType": "rank", "tk": 12, "kills": 4, "assists": 0,
    }
    with pytest.raises(GameEditError):
        validate_result_edit({"imagePath": "x.jpg"}, cobalt=False)


@pytest.mark.parametrize("bad", [
    {"placement": 0}, {"placement": 100}, {"placement": "3"}, {"placement": True}, {"kills": -1}, {"tk": 1.5},
    {"matchType": "casual"}, {"outcome": 5},
])
def test_result_edit_rejects_bad_values(bad):
    with pytest.raises(GameEditError):
        validate_result_edit(bad, cobalt=False)


def test_empty_values_clear_the_field():
    edit = validate_result_edit({"placement": None, "outcome": "", "tk": None}, cobalt=False)
    assert edit == {"placement": None, "outcome": None, "tk": None}


def test_cobalt_outcome_is_victory_or_defeat_only():
    assert validate_result_edit({"outcome": "승리"}, cobalt=True) == {"outcome": "승리"}
    with pytest.raises(GameEditError):
        validate_result_edit({"outcome": "실험 종료"}, cobalt=True)


def test_lock_result_merges_into_existing_result_and_locks():
    game = {"matchResult": {"placement": 5, "imagePath": "result.jpg", "kills": 2}}
    lock_result(game, {"placement": 1})
    assert game["matchResult"] == {"placement": 1, "imagePath": "result.jpg", "kills": 2}
    assert game["matchResultSource"] == "manual"


def test_lock_result_creates_a_result_for_a_game_without_one():
    game = {"matchResult": None}
    lock_result(game, {"placement": 2, "matchType": "normal"})
    assert game["matchResult"] == {"placement": 2, "matchType": "normal"} and game["matchResultSource"] == "manual"


def test_carry_user_fields_keeps_pin_title_and_locked_result():
    old = {"pinned": True, "title": "내 제목", "matchResult": {"placement": 1}, "matchResultSource": "manual"}
    new = {"matchResult": {"placement": 7}}
    carry_user_fields(old, new)
    assert new == {"pinned": True, "title": "내 제목", "matchResult": {"placement": 1}, "matchResultSource": "manual"}


def test_carry_user_fields_leaves_an_unlocked_result_alone():
    new = {"matchResult": {"placement": 7}}
    carry_user_fields({"matchResult": {"placement": 1}}, new)
    assert new == {"matchResult": {"placement": 7}}


def _clip(tmp_path, name, **meta):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(meta), encoding="utf-8")
    return path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_sync_clip_results_writes_edit_and_lock_but_keeps_the_clips_own_image(tmp_path):
    clip = _clip(tmp_path, "a", matchResult={"placement": 5, "kills": 2, "imagePath": ".thumbs/r.jpg"})
    sync_clip_results([clip], {"placement": 1}, locked=True)
    assert read(clip)["matchResult"] == {"placement": 1, "kills": 2, "imagePath": ".thumbs/r.jpg"}
    assert read(clip)["matchResultSource"] == "manual"


def test_sync_clip_results_unlock_clears_only_the_lock(tmp_path):
    clip = _clip(tmp_path, "a", matchResult={"placement": 1}, matchResultSource="manual")
    sync_clip_results([clip], None, locked=False)
    assert read(clip)["matchResult"] == {"placement": 1} and read(clip)["matchResultSource"] is None


def test_sync_clip_results_skips_unreadable_files(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    sync_clip_results([bad, tmp_path / "missing.json"], {"placement": 1}, locked=True)
