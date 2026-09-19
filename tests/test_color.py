import numpy as np

from lumia_briefing_room.detect.color import channel_stats, vivid_mask


def _solid(rgb: tuple[int, int, int], shape=(4, 4)) -> np.ndarray:
    frame = np.zeros((*shape, 3), dtype=np.uint8)
    frame[..., 0] = rgb[0]
    frame[..., 1] = rgb[1]
    frame[..., 2] = rgb[2]
    return frame


def test_channel_stats_computes_brightness_and_saturation():
    frame = _solid((255, 150, 20), shape=(1, 1))
    stats = channel_stats(frame)
    assert stats.v[0, 0] == 255
    assert stats.s[0, 0] == 235
    assert stats.r[0, 0] == 255
    assert stats.g[0, 0] == 150
    assert stats.b[0, 0] == 20


def test_vivid_mask_true_for_bright_saturated_pixel():
    frame = _solid((255, 150, 20), shape=(1, 1))
    stats = channel_stats(frame)
    mask = vivid_mask(stats, v_min=90, s_min=60)
    assert mask[0, 0]


def test_vivid_mask_false_for_dark_pixel():
    frame = _solid((30, 20, 10), shape=(1, 1))
    stats = channel_stats(frame)
    mask = vivid_mask(stats, v_min=90, s_min=60)
    assert not mask[0, 0]


def test_vivid_mask_false_for_grey_pixel():
    frame = _solid((200, 195, 190), shape=(1, 1))
    stats = channel_stats(frame)
    mask = vivid_mask(stats, v_min=90, s_min=60)
    assert not mask[0, 0]
