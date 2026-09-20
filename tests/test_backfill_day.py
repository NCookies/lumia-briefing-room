import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from backfill_day import apply_game_day, most_common_day  # noqa: E402


def meta(**kw):
    base = {"title": "낮 묘지 교전", "dayNight": "day", "region": "묘지", "gameDay": None,
            "phaseIndex": None, "reviveCost": None, "userLabel": "pvp"}
    base.update(kw)
    return base


def test_apply_sets_day_phase_revive_cost_and_default_title():
    result = apply_game_day(meta(), 4)

    assert result["gameDay"] == 4
    assert result["phaseIndex"] == 6
    assert result["reviveCost"] == "credit"
    assert result["title"] == "4일차 낮 묘지 교전"


def test_apply_uses_free_revive_up_to_day_two_night():
    result = apply_game_day(meta(dayNight="night", title="밤 묘지 교전"), 2)

    assert result["phaseIndex"] == 3
    assert result["reviveCost"] == "free"
    assert result["title"] == "2일차 밤 묘지 교전"


def test_apply_keeps_a_title_the_user_renamed():
    result = apply_game_day(meta(title="내가 붙인 제목"), 4)

    assert result["title"] == "내가 붙인 제목"
    assert result["gameDay"] == 4


def test_apply_keeps_labels_and_other_fields():
    assert apply_game_day(meta(pinned=True), 4)["userLabel"] == "pvp"
    assert apply_game_day(meta(pinned=True), 4)["pinned"] is True


def test_apply_does_nothing_when_the_day_is_unknown():
    original = meta()

    assert apply_game_day(original, None) == original


def test_apply_without_day_night_leaves_phase_empty():
    result = apply_game_day(meta(dayNight=None, title="알 수 없음 묘지 교전"), 3)

    assert result["gameDay"] == 3
    assert result["phaseIndex"] is None


def test_most_common_day_picks_the_mode_and_ignores_unread_samples():
    assert most_common_day([4, 4, None, 5, 4, None]) == 4
    assert most_common_day([None, None]) is None
    assert most_common_day([]) is None


def test_padded_crop_is_even_aligned_and_covers_the_roi_exactly():
    from backfill_day import padded_crop
    from lumia_briefing_room.profiles.models import Roi

    filter_str, rows, cols = padded_crop(Roi(1129, 7, 1144, 32))

    assert filter_str == "crop=16:26:1128:6"
    assert (rows.start, rows.stop) == (1, 26)
    assert (cols.start, cols.stop) == (1, 16)


def test_apply_replaces_a_previous_auto_title_that_had_the_wrong_day():
    result = apply_game_day(meta(title="7일차 낮 묘지 교전", gameDay=7), 6)

    assert result["gameDay"] == 6
    assert result["title"] == "6일차 낮 묘지 교전"


def test_apply_keeps_a_renamed_title_even_when_the_day_changes():
    assert apply_game_day(meta(title="내 제목", gameDay=7), 6)["title"] == "내 제목"
