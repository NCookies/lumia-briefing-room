import numpy as np

from lumia_briefing_room.detect.ultimate import BLUE_MIN, BLUE_OVER_RED, blue_tint_ratio


def _solid(rgb: tuple[int, int, int], shape=(20, 20)) -> np.ndarray:
    frame = np.zeros((*shape, 3), dtype=np.uint8)
    frame[..., 0] = rgb[0]
    frame[..., 1] = rgb[1]
    frame[..., 2] = rgb[2]
    return frame


def test_blue_tint_ratio_is_zero_for_a_warm_ready_icon():
    # 실측(2026-09-22, 134809_01 t=5s): 준비 상태 파란비율 0.000
    frame = _solid((200, 120, 40))
    assert blue_tint_ratio(frame) == 0.0


def test_blue_tint_ratio_is_high_for_a_cooldown_overlay():
    # 실측(2026-09-22, 134809_01 t=60s, 쿨타임 37): 파란비율 0.269
    frame = _solid((40, 90, 180))
    assert blue_tint_ratio(frame) == 1.0


def test_blue_tint_ratio_ignores_blue_just_under_the_brightness_floor():
    frame = _solid((0, 0, BLUE_MIN - 1))
    assert blue_tint_ratio(frame) == 0.0


def test_blue_tint_ratio_requires_blue_to_dominate_red_by_the_margin():
    frame = _solid((BLUE_MIN, 0, BLUE_MIN + BLUE_OVER_RED - 1))
    assert blue_tint_ratio(frame) == 0.0


def test_blue_tint_ratio_is_the_fraction_of_matching_pixels():
    frame = _solid((200, 120, 40), shape=(10, 10))
    frame[:5, :] = (40, 90, 180)  # 절반만 쿨타임 오버레이
    assert blue_tint_ratio(frame) == 0.5
