import pytest

from lumia_briefing_room.pipeline import game_candidates as gcand


def cand(cid="k_01", start=10.0, end=40.0, certain=False, user=None):
    return {"id": cid, "start": start, "end": end, "certain": certain, "tags": [], "user": user or {}}


def test_effective_range_prefers_the_users_adjustment():
    assert gcand.effective_range(cand(), 600.0) == (10.0, 40.0)
    assert gcand.effective_range(cand(user={"start": 5.0, "end": 50.0}), 600.0) == (5.0, 50.0)


def test_effective_range_is_clamped_to_the_video():
    assert gcand.effective_range(cand(start=-3.0, end=700.0), 600.0) == (0.0, 600.0)


def test_edit_stores_the_range_in_the_user_section():
    c = cand()
    gcand.apply_edit(c, {"start": 12.0, "end": 45.5}, 600.0)
    assert c["user"] == {"start": 12.0, "end": 45.5}
    assert c["start"] == 10.0  # 자동 검출 값은 그대로 둔다


def test_edit_can_dismiss_and_restore():
    c = cand()
    gcand.apply_edit(c, {"dismissed": True}, 600.0)
    assert c["user"]["dismissed"] is True
    gcand.apply_edit(c, {"dismissed": False}, 600.0)
    assert "dismissed" not in c["user"]


def test_edit_label_accepts_known_values_and_null_clears_it():
    c = cand()
    gcand.apply_edit(c, {"label": "combat"}, 600.0)
    assert c["user"]["label"] == "combat"
    gcand.apply_edit(c, {"label": None}, 600.0)
    assert "label" not in c["user"]
    with pytest.raises(ValueError):
        gcand.apply_edit(c, {"label": "weird"}, 600.0)


@pytest.mark.parametrize("patch", [{"start": 50.0, "end": 40.0}, {"start": 10.0, "end": 10.5}, {"start": -1.0}, {"end": 9999.0}])
def test_invalid_ranges_are_rejected(patch):
    with pytest.raises(ValueError):
        gcand.apply_edit(cand(), patch, 600.0)


def test_partial_range_edit_is_checked_against_the_other_side():
    c = cand(start=10.0, end=40.0)
    with pytest.raises(ValueError):
        gcand.apply_edit(c, {"start": 45.0}, 600.0)


def test_unknown_fields_are_rejected():
    with pytest.raises(ValueError):
        gcand.apply_edit(cand(), {"savedClipId": "x"}, 600.0)


def test_new_user_candidate_gets_the_next_id_and_is_certain_free():
    game = {"gameKey": "20260930_100000", "userCandidates": [{"id": "20260930_100000_u1"}]}
    c = gcand.new_user_candidate(game, 100.0, 130.0, 600.0, title="내가 찾은 교전")
    assert c["id"] == "20260930_100000_u2"
    assert (c["start"], c["end"], c["certain"], c["title"]) == (100.0, 130.0, False, "내가 찾은 교전")
    assert c["user"] == {}


def test_all_candidates_lists_auto_then_user_ones():
    game = {"candidates": [cand("a")], "userCandidates": [cand("u")]}
    assert [c["id"] for c in gcand.all_candidates(game)] == ["a", "u"]


def test_batch_selection_skips_dismissed_and_already_saved():
    game = {
        "candidates": [
            cand("a", certain=True),
            cand("b", certain=False),
            cand("c", certain=True, user={"dismissed": True}),
            cand("d", certain=True, user={"savedClipId": "clip"}),
        ],
        "userCandidates": [cand("u")],
    }
    assert [c["id"] for c in gcand.select_for_batch(game, "all")] == ["a", "b", "u"]
    assert [c["id"] for c in gcand.select_for_batch(game, "certain")] == ["a"]
    assert [c["id"] for c in gcand.select_for_batch(game, "ids", ids=["b", "d", "zzz"])] == ["b"]


def test_unknown_batch_mode_is_rejected():
    with pytest.raises(ValueError):
        gcand.select_for_batch({"candidates": []}, "weird")
