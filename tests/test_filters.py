from lumia_briefing_room.config import FilterConfig, TagFilter
from lumia_briefing_room.detect.types import CombatInterval
from lumia_briefing_room.pipeline.filters import apply_filter


def ci(start, end, tags, day_night="day", died=False):
    return CombatInterval(
        start=start, end=end, tags=frozenset(tags),
        k_delta=1 if "kill" in tags else 0,
        a_delta=1 if "assist" in tags else 0,
        died=died, day_night=day_night, confidence=1.0,
    )


KILL = ci(0, 20, {"kill"})
ASSIST = ci(0, 20, {"assist"})
DEATH = ci(0, 20, {"death"})
NO_RESULT = ci(0, 20, {"no_result"})
ALL_FOUR = [KILL, ASSIST, DEATH, NO_RESULT]


def test_preset_all_passes_everything():
    result = apply_filter(ALL_FOUR, FilterConfig(preset="all"))
    assert result == ALL_FOUR


def test_preset_won_keeps_kill_and_assist_only():
    result = apply_filter(ALL_FOUR, FilterConfig(preset="won"))
    assert result == [KILL, ASSIST]


def test_preset_lost_keeps_death_only():
    result = apply_filter(ALL_FOUR, FilterConfig(preset="lost"))
    assert result == [DEATH]


def test_preset_custom_uses_explicit_tags_include():
    cfg = FilterConfig(preset="custom", tags=TagFilter(include=["death"]))
    result = apply_filter(ALL_FOUR, cfg)
    assert result == [DEATH]


def test_preset_custom_exclude_removes_matching():
    cfg = FilterConfig(preset="custom", tags=TagFilter(exclude=["no_result"]))
    result = apply_filter(ALL_FOUR, cfg)
    assert result == [KILL, ASSIST, DEATH]


def test_kill_and_death_together_passes_won_and_lost():
    kill_and_death = ci(0, 20, {"kill", "death"})
    assert apply_filter([kill_and_death], FilterConfig(preset="won")) == [kill_and_death]
    assert apply_filter([kill_and_death], FilterConfig(preset="lost")) == [kill_and_death]


def test_min_duration_filters_short_intervals_without_hard_evidence():
    short = ci(0, 3, {"no_result"})
    long = ci(0, 10, {"no_result"})
    cfg = FilterConfig(preset="all", min_duration_sec=4)
    assert apply_filter([short, long], cfg) == [long]


def test_min_duration_never_drops_kill_assist_or_death_intervals():
    """킬·어시·사망은 확정 증거다. 배지가 잠깐만 켜진 1~3초 구간이어도 그 교전은 클립이 되어야 한다(재현율 우선)."""
    cfg = FilterConfig(preset="all", min_duration_sec=4)
    short_kill = ci(0, 1, {"kill"})
    short_assist = ci(0, 2, {"assist", "teammate_death"})
    short_death = ci(0, 3, {"death"})
    short_hunt = ci(0, 3, {"no_result"})

    kept = apply_filter([short_kill, short_assist, short_death, short_hunt], cfg)

    assert kept == [short_kill, short_assist, short_death]


def test_max_duration_still_applies_to_intervals_with_hard_evidence():
    cfg = FilterConfig(preset="all", max_duration_sec=50)
    assert apply_filter([ci(0, 100, {"kill"})], cfg) == []


def test_max_duration_filters_long_intervals():
    short = ci(0, 10, {"kill"})
    long = ci(0, 100, {"kill"})
    cfg = FilterConfig(preset="all", max_duration_sec=50)
    assert apply_filter([short, long], cfg) == [short]


def test_day_night_filter_day_only():
    day = ci(0, 10, {"kill"}, day_night="day")
    night = ci(0, 10, {"kill"}, day_night="night")
    cfg = FilterConfig(preset="all", day_night="day")
    assert apply_filter([day, night], cfg) == [day]


def test_day_night_filter_rejects_unknown_when_specific_requested():
    unknown = ci(0, 10, {"kill"}, day_night=None)
    cfg = FilterConfig(preset="all", day_night="day")
    assert apply_filter([unknown], cfg) == []


def test_day_night_any_passes_unknown():
    unknown = ci(0, 10, {"kill"}, day_night=None)
    cfg = FilterConfig(preset="all", day_night="any")
    assert apply_filter([unknown], cfg) == [unknown]


def test_game_mode_filter():
    cfg = FilterConfig(preset="all", game_mode="battle_royale")
    assert apply_filter([KILL], cfg, game_mode="cobalt") == []
    assert apply_filter([KILL], cfg, game_mode="battle_royale") == [KILL]


def test_game_mode_any_passes_regardless():
    cfg = FilterConfig(preset="all", game_mode="any")
    assert apply_filter([KILL], cfg, game_mode="cobalt") == [KILL]


def test_phase_min_filters_by_phase_index():
    cfg = FilterConfig(preset="all", phase_min=4)
    result = apply_filter([KILL, ASSIST], cfg, phase_indices=[2, 5])
    assert result == [ASSIST]


def test_phase_max_filters_by_phase_index():
    cfg = FilterConfig(preset="all", phase_max=3)
    result = apply_filter([KILL, ASSIST], cfg, phase_indices=[2, 5])
    assert result == [KILL]


def test_revive_cost_free_means_phase_le_3():
    cfg = FilterConfig(preset="all", revive_cost="free")
    result = apply_filter([KILL, ASSIST], cfg, phase_indices=[3, 4])
    assert result == [KILL]


def test_revive_cost_credit_means_phase_ge_4():
    cfg = FilterConfig(preset="all", revive_cost="credit")
    result = apply_filter([KILL, ASSIST], cfg, phase_indices=[3, 4])
    assert result == [ASSIST]


def test_phase_filter_rejects_when_phase_unknown():
    cfg = FilterConfig(preset="all", phase_min=4)
    result = apply_filter([KILL], cfg, phase_indices=[None])
    assert result == []


def test_phase_filter_rejects_when_phase_indices_not_provided_at_all():
    cfg = FilterConfig(preset="all", revive_cost="credit")
    result = apply_filter([KILL], cfg)
    assert result == []


def test_no_phase_constraint_ignores_missing_phase_indices():
    cfg = FilterConfig(preset="all")
    assert apply_filter([KILL], cfg) == [KILL]


def test_empty_intervals_returns_empty():
    assert apply_filter([], FilterConfig(preset="all")) == []
