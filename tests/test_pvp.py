from lumia_briefing_room.config import Config, FilterConfig, dataclass_from_camel_dict, dataclass_to_camel_dict
from lumia_briefing_room.detect.pvp import score_interval
from lumia_briefing_room.detect.types import CombatInterval
from lumia_briefing_room.pipeline.filters import apply_filter


def iv(*, k=0, a=0, died=False, team=0, rings=None, start=0.0, end=20.0, day=None, ultimate=None):
    tags = set()
    if k: tags.add("kill")
    if a: tags.add("assist")
    if died: tags.add("death")
    if team: tags.add("teammate_death")
    return CombatInterval(
        start=start, end=end, tags=frozenset(tags or {"no_result"}), k_delta=k, a_delta=a,
        died=died, day_night="day", confidence=1.0, teammate_deaths=team, enemy_ring_mean=rings, game_day=day,
        ultimate_delta=ultimate,
    )


WEIGHTS = {"enemyRings": 0.7, "death": 0.9, "teammateDeath": 0.8, "ultimateUsed": 0.6}


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


def test_default_weights_do_not_use_the_minimap_because_labels_showed_no_separation():
    from lumia_briefing_room.detect.pvp import DEFAULT_WEIGHTS

    assert DEFAULT_WEIGHTS["enemyRings"] == 0.0
    assert FilterConfig().pvp_weights["enemyRings"] == 0.0
    assert score_interval(iv(rings=3.0), DEFAULT_WEIGHTS).score == 0.0


def test_default_weights_use_ultimate_because_labels_showed_strong_separation():
    # AUC(delta) 0.914 (라벨 110개, 2026-09-22) - 미니맵(0.53)과 반대로 채택했다.
    from lumia_briefing_room.detect.pvp import DEFAULT_WEIGHTS

    assert DEFAULT_WEIGHTS["ultimateUsed"] == 0.6
    assert FilterConfig().pvp_weights["ultimateUsed"] == 0.6
    assert score_interval(iv(ultimate=0.5), DEFAULT_WEIGHTS).score == 0.6


def test_a_zero_weighted_signal_is_not_listed_as_evidence():
    assert score_interval(iv(rings=3.0), {"enemyRings": 0.0}).signals == []
    assert score_interval(iv(died=True, rings=3.0), {"enemyRings": 0.0, "death": 0.9}).signals == ["death"]


SPLIT_WEIGHTS = {**WEIGHTS, "teammateDeathSplit": 0.5}


def test_teammate_death_on_free_revive_days_is_discounted_because_teammates_split_and_die_alone():
    early = score_interval(iv(team=1, day=2), SPLIT_WEIGHTS)
    later = score_interval(iv(team=1, day=3), SPLIT_WEIGHTS)
    unknown = score_interval(iv(team=1, day=None), SPLIT_WEIGHTS)

    assert early.score == 0.5 and early.signals == ["teammate_death"]
    assert later.score == 0.8
    assert unknown.score == 0.8


def test_the_split_discount_does_not_touch_my_own_death_or_kills():
    assert score_interval(iv(team=1, died=True, day=1), SPLIT_WEIGHTS).score == 0.9
    assert score_interval(iv(team=1, k=1, day=1), SPLIT_WEIGHTS).score == 1.0


def test_ultimate_used_is_evidence_when_the_cooldown_jump_clears_the_threshold():
    # 라벨 110개 검증(2026-09-22, scripts/probe/eval_ultimate_signal.py): AUC(delta) 0.914.
    result = score_interval(iv(ultimate=0.48), WEIGHTS)

    assert result.score == 0.6
    assert result.signals == ["ultimate_used"]


def test_ultimate_used_is_not_evidence_below_the_delta_threshold():
    # 캐릭터마다 R 아이콘 원화의 파란기 베이스라인이 달라 작은 델타는 잡음이다.
    result = score_interval(iv(ultimate=0.05), WEIGHTS)

    assert result.score == 0.0
    assert result.signals == []


def test_ultimate_used_is_not_evidence_when_never_read():
    assert score_interval(iv(ultimate=None), WEIGHTS).signals == []


def test_ultimate_used_loses_to_stronger_confirmed_evidence():
    result = score_interval(iv(died=True, ultimate=0.5), WEIGHTS)

    assert result.score == 0.9
    assert result.signals == ["death", "ultimate_used"]


def test_kill_still_wins_outright_even_with_ultimate_evidence():
    assert score_interval(iv(k=1, ultimate=0.5), WEIGHTS).score == 1.0
