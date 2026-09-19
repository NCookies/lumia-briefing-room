import numpy as np

from lumia_briefing_room.detect.daynight import MIN_ICON_PX, classify_day_night, read_day_night


def _solid(rgb: tuple[int, int, int], shape=(15, 15)) -> np.ndarray:
    frame = np.zeros((*shape, 3), dtype=np.uint8)
    frame[..., 0] = rgb[0]
    frame[..., 1] = rgb[1]
    frame[..., 2] = rgb[2]
    return frame


def test_classify_counts_yellow_for_sun_color():
    frame = _solid((255, 200, 20))
    counts = classify_day_night(frame)
    assert counts.yellow == 225
    assert counts.purple == 0


def test_classify_counts_purple_for_moon_color():
    frame = _solid((150, 60, 200))
    counts = classify_day_night(frame)
    assert counts.purple == 225
    assert counts.yellow == 0


def test_read_day_night_returns_day_for_sun():
    frame = _solid((255, 200, 20))
    assert read_day_night(frame) == "day"


def test_read_day_night_returns_night_for_moon():
    frame = _solid((150, 60, 200))
    assert read_day_night(frame) == "night"


def test_read_day_night_none_when_icon_absent():
    frame = _solid((20, 20, 20))
    assert read_day_night(frame) is None


def test_read_day_night_picks_larger_when_background_bleeds_through():
    # research §4.9: 상단 바가 반투명이라 배경이 섞여, 밤인데도 낮 색이 일부 섞일 수 있다.
    # "큰 쪽 비교"로 판정해야 한다.
    frame = np.zeros((15, 15, 3), dtype=np.uint8)
    frame[:10, :] = (150, 60, 200)   # 보라 150px (밤 아이콘)
    frame[10:, :] = (255, 200, 20)   # 노랑 75px (배경 간섭)
    assert read_day_night(frame) == "night"


def test_min_icon_px_is_below_smallest_measured_value():
    # research §4.9 실측: 밤 보라 픽셀 최소 198. 그보다 낮은 값도 놓치지 않아야 한다.
    assert MIN_ICON_PX < 198
