import numpy as np
import pytest

from lumia_briefing_room.detect.ultimate import BLUE_MIN, BLUE_OVER_RED, blue_tint_ratio, is_locked


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


def _with_red_x(shape, background: tuple[int, int, int], red_frac: float) -> np.ndarray:
    frame = _solid(background, shape=shape)
    n = shape[0] * shape[1]
    n_red = int(round(n * red_frac))
    flat = frame.reshape(-1, 3)
    flat[:n_red] = (200, 20, 20)
    return flat.reshape(*shape, 3)


def test_is_locked_true_for_dark_icon_with_a_thin_red_x_overlay():
    # 실측(2026-09-23, MARTIN/BIHYUN 잠김 상태): red_frac 0.054~0.055, v_median 36~40.
    frame = _with_red_x((20, 20), background=(40, 40, 40), red_frac=0.055)
    assert is_locked(frame) is True


def test_is_locked_false_for_a_bright_unlocked_icon_even_with_no_red():
    # 실측(MARTIN 해금 상태): v_median 68, red_frac 0.
    frame = _solid((90, 90, 60), shape=(20, 20))
    assert is_locked(frame) is False


def test_is_locked_false_for_a_dark_unlocked_icon_with_no_red():
    # 실측(CHIAR 해금 상태): 원화 자체가 어둡지만(v_median 13) 빨간기가 전혀 없다.
    frame = _solid((30, 25, 35), shape=(20, 20))
    assert is_locked(frame) is False


def test_is_locked_false_for_a_naturally_red_themed_unlocked_icon():
    # 실측(BIHYUN 해금 상태, 불 테마 원화): red_frac 0.30 - 얇은 X 오버레이보다 훨씬 넓다.
    frame = _with_red_x((20, 20), background=(90, 90, 90), red_frac=0.30)
    assert is_locked(frame) is False


def test_max_rise_ignores_a_cooldown_that_was_already_running_before_the_clip():
    # 실사용 오탐(2026-09-23, 연구소 버니스·묘지 마르티나): 클립이 시작될 때 이미
    # 직전 교전에서 쓴 궁의 쿨타임이 돌고 있었을 뿐인데, 범위(max-min)로 재면 이걸
    # "이번에 썼다"로 잘못 본다. 시간순으로 단조 감소하기만 하는 시퀀스는 0에 가까워야 한다.
    from lumia_briefing_room.detect.ultimate import max_rise

    assert max_rise([0.56, 0.393, 0.379, 0.373]) == pytest.approx(0.0)


def test_max_rise_catches_a_genuine_use_partway_through_the_clip():
    # 실사용(묘지 마르티나 04번 클립): 준비 상태(낮은 값)로 내려갔다가 그 이후 쿨타임
    # 진입(높은 값)으로 다시 오르면 그 상승분이 진짜 신호다.
    from lumia_briefing_room.detect.ultimate import max_rise

    assert max_rise([0.229, 0.185, 0.164, 0.116, 0.02, 0.071, 0.219, 0.221]) == pytest.approx(0.221 - 0.02)


def test_max_rise_of_empty_or_single_value_is_zero():
    from lumia_briefing_room.detect.ultimate import max_rise

    assert max_rise([]) == 0.0
    assert max_rise([0.5]) == 0.0


def test_max_rise_equals_range_when_the_low_point_comes_first():
    from lumia_briefing_room.detect.ultimate import max_rise

    assert max_rise([0.0, 0.1, 0.48, 0.3]) == pytest.approx(0.48)
