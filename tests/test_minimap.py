import cv2
import numpy as np

from lumia_briefing_room.detect.minimap import count_enemy_rings

RED = (40, 40, 230)
YELLOW = (40, 220, 230)
GREEN = (60, 220, 60)
BLUE = (230, 140, 40)


def _map(rings):
    img = np.full((310, 340, 3), 60, np.uint8)
    for (x, y), bgr in rings:
        cv2.circle(img, (x, y), 12, (8, 8, 8), -1)
        cv2.circle(img, (x, y), 12, bgr, 3)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def test_counts_only_red_rings():
    rgb = _map([((80, 80), RED), ((200, 90), RED), ((150, 200), YELLOW), ((260, 240), GREEN), ((60, 250), BLUE)])

    assert count_enemy_rings(rgb) == 2


def test_no_enemy_when_only_allies():
    rgb = _map([((80, 80), YELLOW), ((200, 150), GREEN)])

    assert count_enemy_rings(rgb) == 0


def test_empty_minimap_has_no_enemies():
    assert count_enemy_rings(_map([])) == 0


def test_a_flat_red_zone_without_rings_is_not_an_enemy():
    img = np.full((310, 340, 3), 60, np.uint8)
    img[40:200, 30:250] = (200, 40, 40)

    assert count_enemy_rings(img) == 0


def test_count_rings_separates_enemy_and_ally_rings():
    from lumia_briefing_room.detect.minimap import count_rings

    rgb = _map([((80, 80), RED), ((200, 90), YELLOW), ((150, 200), GREEN), ((260, 240), BLUE)])
    counts = count_rings(rgb)

    assert counts.enemy == 1
    assert counts.ally == 3


def test_count_rings_of_an_empty_map_is_zero():
    from lumia_briefing_room.detect.minimap import count_rings

    counts = count_rings(_map([]))

    assert (counts.enemy, counts.ally) == (0, 0)
