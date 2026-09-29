import json
from datetime import datetime, timezone

from lumia_briefing_room.detect.types import CombatInterval
from lumia_briefing_room.pipeline import game_store as gs

START = datetime(2026, 9, 30, 0, 24, 0, tzinfo=timezone.utc)


def ci(start, end, tags, **kw):
    return CombatInterval(
        start=start, end=end, tags=frozenset(tags), k_delta=1 if "kill" in tags else 0,
        a_delta=0, died="death" in tags, day_night="day", confidence=1.0, **kw,
    )


def test_game_key_is_the_match_start_timestamp():
    assert gs.game_key(START) == "20260930_002400"


def test_certain_candidates_are_the_ones_with_kill_assist_or_death():
    assert gs.is_certain(frozenset({"kill"}))
    assert gs.is_certain(frozenset({"assist", "teammate_death"}))
    assert gs.is_certain(frozenset({"death"}))
    assert not gs.is_certain(frozenset({"no_result"}))
    assert not gs.is_certain(frozenset({"teammate_death"}))


def test_auto_mode_saves_every_candidate_when_the_full_video_exists():
    plans = ["a", "b"]
    certain = {"a": True, "b": False}
    assert gs.plans_to_save(plans, "auto", True, is_certain=certain.get) == ["a", "b"]


def test_manual_mode_saves_nothing_when_the_full_video_exists():
    assert gs.plans_to_save(["a"], "manual", True, is_certain=lambda p: True) == []


def test_without_a_full_video_only_certain_candidates_are_saved_in_any_mode():
    certain = {"a": True, "b": False}
    for mode in ("auto", "manual"):
        assert gs.plans_to_save(["a", "b"], mode, False, is_certain=certain.get) == ["a"]


def test_unknown_save_mode_behaves_like_auto():
    assert gs.plans_to_save(["a"], "weird", True, is_certain=lambda p: False) == ["a"]


def test_room_check_needs_size_plus_margin():
    assert gs.has_room(free_bytes=10 * 2**30, needed_bytes=5 * 2**30, margin_bytes=2**30)
    assert not gs.has_room(free_bytes=5 * 2**30, needed_bytes=5 * 2**30, margin_bytes=2**30)


def test_candidate_times_are_relative_to_the_full_video():
    cand = gs.candidate_dict(
        "20260930_002400_01", interval=ci(110.0, 130.0, {"kill"}), start=105.0, end=138.0,
        preroll_source="combat", title="1일차 낮 교전", offset_sec=100.0, pvp_score=1.0, pvp_signals=["kill_delta"],
        clip_id=None,
    )
    assert (cand["start"], cand["end"]) == (5.0, 38.0)
    assert cand["combatStart"] == 10.0 and cand["combatEnd"] == 30.0
    assert cand["certain"] is True
    assert cand["tags"] == ["kill"]
    assert cand["user"] == {}


def test_candidate_before_the_full_video_start_is_clamped_to_zero():
    cand = gs.candidate_dict(
        "x", interval=ci(2.0, 9.0, {"kill"}), start=-3.0, end=15.0, preroll_source="combat",
        title="t", offset_sec=0.0, pvp_score=0.0, pvp_signals=[], clip_id=None,
    )
    assert cand["start"] == 0.0


def test_saved_clip_id_lands_in_the_user_section():
    cand = gs.candidate_dict(
        "x", interval=ci(2.0, 9.0, {"kill"}), start=0.0, end=15.0, preroll_source="combat",
        title="t", offset_sec=0.0, pvp_score=0.0, pvp_signals=[], clip_id="20260930_002400_01",
    )
    assert cand["user"] == {"savedClipId": "20260930_002400_01"}


def test_markers_are_relative_and_sorted():
    markers = gs.markers_dict([(130.0, "kill"), (110.0, "death")], offset_sec=100.0)
    assert markers == [{"t": 10.0, "kind": "death"}, {"t": 30.0, "kind": "kill"}]


def test_write_game_json_is_atomic_and_readable(tmp_path):
    folder = tmp_path / "games" / "k"
    gs.write_game_json(folder, {"gameKey": "k", "candidates": []})
    assert json.loads((folder / "game.json").read_text(encoding="utf-8"))["gameKey"] == "k"
    assert not list(folder.glob("*.tmp"))
