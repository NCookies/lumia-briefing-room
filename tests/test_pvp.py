from lumia_briefing_room.config import Config, FilterConfig, dataclass_from_camel_dict, dataclass_to_camel_dict
from lumia_briefing_room.detect.pvp import score_interval
from lumia_briefing_room.detect.types import CombatInterval
from lumia_briefing_room.pipeline.filters import apply_filter


def iv(*, k=0, a=0, died=False, team=0, rings=None, start=0.0, end=20.0):
    tags = set()
    if k: tags.add("kill")
    if a: tags.add("assist")
    if died: tags.add("death")
    if team: tags.add("teammate_death")
    return CombatInterval(
        start=start, end=end, tags=frozenset(tags or {"no_result"}), k_delta=k, a_delta=a,
        died=died, day_night="day", confidence=1.0, teammate_deaths=team, enemy_ring_mean=rings,
    )


WEIGHTS = {"enemyRings": 0.7, "death": 0.9, "teammateDeath": 0.8}


def test_kill_and_assist_are_certain_because_only_players_count():
    for interval, signal in ((iv(k=1), "kill_delta"), (iv(a=2), "assist_delta")):
        result = score_interval(interval, WEIGHTS)
        assert result.score == 1.0
        assert signal in result.signals


def test_deaths_are_strong_but_not_certain_since_monsters_and_the_zone_also_kill():
    mine = score_interval(iv(died=True), WEIGHTS)
    mate = score_interval(iv(team=1), WEIGHTS)

    assert mine.score == 0.9 and mine.signals == ["death"]
    assert mate.score == 0.8 and mate.signals == ["teammate_death"]


def test_strongest_evidence_wins_and_every_signal_is_listed():
    result = score_interval(iv(died=True, team=1, rings=3.0), WEIGHTS)

    assert result.score == 0.9
    assert result.signals == ["death", "teammate_death", "enemy_rings"]


def test_confirmed_evidence_beats_the_minimap_estimate():
    result = score_interval(iv(k=1, rings=0.0), WEIGHTS)

    assert result.score == 1.0
    assert "enemy_rings" not in result.signals


def test_no_evidence_scores_zero():
    assert score_interval(iv(), WEIGHTS).score == 0.0
    assert score_interval(iv(), WEIGHTS).signals == []
    assert score_interval(iv(rings=0.0), WEIGHTS).score == 0.0


def test_enemy_rings_scale_up_to_the_weight():
    half = score_interval(iv(rings=0.75), WEIGHTS)
    full = score_interval(iv(rings=3.0), WEIGHTS)

    assert half.score == 0.35 and half.signals == ["enemy_rings"]
    assert full.score == 0.7


def test_weights_are_configurable():
    assert score_interval(iv(rings=3.0), {"enemyRings": 0.5}).score == 0.5
    assert score_interval(iv(rings=3.0), {}).score == 0.0
    assert score_interval(iv(died=True), {"death": 0.6}).score == 0.6


def test_min_pvp_score_filters_generation_and_defaults_to_pass_all():
    hunt, fight = iv(rings=0.1), iv(k=1)

    assert apply_filter([hunt, fight], FilterConfig()) == [hunt, fight]
    kept = apply_filter([hunt, fight], FilterConfig(min_pvp_score=0.5))
    assert kept == [fight]


def test_pvp_settings_survive_the_config_round_trip():
    cfg = Config(filter=FilterConfig(min_pvp_score=0.4, pvp_weights={"enemyRings": 0.9}))

    restored = dataclass_from_camel_dict(Config, dataclass_to_camel_dict(cfg))

    assert restored.filter.min_pvp_score == 0.4
    assert restored.filter.pvp_weights == {"enemyRings": 0.9}
