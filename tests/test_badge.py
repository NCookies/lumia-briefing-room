import numpy as np

from lumia_briefing_room.detect.badge import PRESENT_MIN, classify_badge, read_badge


def _solid(rgb: tuple[int, int, int], shape=(20, 20)) -> np.ndarray:
    frame = np.zeros((*shape, 3), dtype=np.uint8)
    frame[..., 0] = rgb[0]
    frame[..., 1] = rgb[1]
    frame[..., 2] = rgb[2]
    return frame


def test_classify_badge_counts_orange_for_combat_color():
    frame = _solid((255, 150, 20))
    counts = classify_badge(frame)
    assert counts.orange == 400
    assert counts.yellow == 0
    assert counts.blue == 0


def test_classify_badge_counts_yellow_for_normal_badge():
    frame = _solid((255, 220, 20))
    counts = classify_badge(frame)
    assert counts.yellow == 400
    assert counts.orange == 0


def test_classify_badge_counts_blue_for_normal_badge():
    frame = _solid((50, 60, 255))
    counts = classify_badge(frame)
    assert counts.blue == 400
    assert counts.orange == 0
    assert counts.yellow == 0


def test_classify_badge_ignores_dark_pixels():
    frame = _solid((20, 15, 10))
    counts = classify_badge(frame)
    assert counts.orange == 0
    assert counts.yellow == 0
    assert counts.blue == 0


def test_read_badge_true_when_orange_dominates():
    frame = _solid((255, 150, 20))
    assert read_badge(frame) is True


def test_read_badge_false_when_blue_dominates():
    frame = _solid((50, 60, 255))
    assert read_badge(frame) is False


def test_read_badge_false_when_yellow_badge_normal():
    frame = _solid((255, 220, 20))
    assert read_badge(frame) is False


def test_read_badge_none_when_dark():
    frame = _solid((20, 15, 10))
    assert read_badge(frame) is None


def test_read_badge_none_when_orange_present_but_below_present_threshold():
    # 주황 픽셀이 ORANGE_MIN(100) 은 넘지만, 배지 전체가 보인다고 보기엔
    # 너무 적다(< PRESENT_MIN). SPEC §2.7: 판정 전에 배지가 보이는지 먼저 확인할 것.
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    frame[:6, :20] = (255, 150, 20)  # 6*20 = 120 px, orange>=100 이지만 PRESENT_MIN 미만
    assert 100 <= 6 * 20 < PRESENT_MIN
    assert read_badge(frame) is None


def test_read_badge_handles_noisy_background_mixed_with_orange():
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    frame[:13, :] = (255, 150, 20)   # 260px orange: ORANGE_MIN, PRESENT_MIN 모두 충족
    frame[13:, :] = (40, 90, 120)    # 배경 노이즈, vivid 조건 불충족
    assert read_badge(frame) is True
