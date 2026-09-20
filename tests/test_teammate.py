import numpy as np

from lumia_briefing_room.detect.teammate import (
    dead_slots,
    new_deaths,
    slot_is_dead,
)

ORANGE = (240, 150, 30)
GREEN = (90, 220, 40)
DARK = (30, 30, 30)


def _bar(*fills):
    a = np.full((16, 58, 3), DARK, np.uint8)
    x = 0
    for rgb, width in fills:
        a[:, x : x + width] = rgb
        x += width
    return a


def test_slot_is_dead_when_bar_is_orange_without_green():
    assert slot_is_dead(_bar((ORANGE, 8))) is True


def test_slot_is_alive_when_bar_is_green():
    assert slot_is_dead(_bar((GREEN, 40))) is False


def test_slot_is_alive_when_bar_has_both_colors():
    assert slot_is_dead(_bar((GREEN, 20), (ORANGE, 8))) is False


def test_slot_is_alive_when_bar_is_empty():
    assert slot_is_dead(_bar()) is False


def test_slot_ignores_a_tiny_orange_speck():
    a = _bar()
    a[0, 0] = ORANGE

    assert slot_is_dead(a) is False


def test_dead_slots_returns_indexes_of_dead_bars():
    alive, dead = _bar((GREEN, 40)), _bar((ORANGE, 8))

    assert dead_slots([alive, dead]) == [1]
    assert dead_slots([dead, dead]) == [0, 1]
    assert dead_slots([alive, alive]) == []


def test_new_deaths_reports_only_transitions_to_dead():
    series = [(0.0, []), (3.0, []), (6.0, [1]), (9.0, [1]), (12.0, [0, 1])]

    assert new_deaths(series) == [(6.0, 1), (12.0, 0)]


def test_new_deaths_ignores_slots_already_dead_at_start():
    assert new_deaths([(0.0, [1]), (3.0, [1])]) == []


def _ring(rgb, fraction=0.3):
    a = np.full((60, 80, 3), (60, 60, 90), np.uint8)
    n = int(a.shape[0] * a.shape[1] * fraction)
    a.reshape(-1, 3)[:n] = rgb
    return a


def test_slot_in_combat_when_the_ring_is_red():
    from lumia_briefing_room.detect.teammate import slot_in_combat

    assert slot_in_combat(_ring((230, 40, 40))) is True


def test_slot_not_in_combat_with_pink_purple_or_blank_rings():
    from lumia_briefing_room.detect.teammate import slot_in_combat

    assert slot_in_combat(_ring((255, 80, 150))) is False
    assert slot_in_combat(_ring((150, 80, 200))) is False
    assert slot_in_combat(_ring((230, 40, 40), 0.005)) is False


def test_combat_slots_excludes_dead_teammates_whose_portrait_is_also_red():
    from lumia_briefing_room.detect.teammate import combat_slots

    red = _ring((230, 40, 40))
    alive_bar, dead_bar = _bar((GREEN, 40)), _bar((ORANGE, 8))

    assert combat_slots([red, red], [alive_bar, dead_bar]) == [0]
    assert combat_slots([red, red], [alive_bar, alive_bar]) == [0, 1]
    assert combat_slots([_ring((150, 80, 200)), red], [alive_bar, alive_bar]) == [1]
