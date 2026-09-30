import cv2
import numpy as np

from lumia_briefing_room.detect.rank import read_rank_digit
from lumia_briefing_room.detect.region import build_region_template, region_score

H, W = 112, 85


def digit_image(text, color=(255, 170, 0), shift=0):
    img = np.full((H, W, 3), 25, np.uint8)
    cv2.putText(img, text, (12 + shift, 92), cv2.FONT_HERSHEY_SIMPLEX, 3.2, color, 8, cv2.LINE_AA)
    return img


TEMPLATES = {n: build_region_template([region_score(digit_image(n))]) for n in ("1", "3")}


def test_reads_a_digit_that_has_a_template_even_when_shifted_or_recolored():
    assert read_rank_digit(digit_image("3", shift=4), TEMPLATES) == 3
    assert read_rank_digit(digit_image("1", color=(0, 180, 255)), TEMPLATES) == 1


def test_digit_without_a_template_is_unreadable_rather_than_confused_with_another():
    assert read_rank_digit(digit_image("5"), TEMPLATES) is None
    assert read_rank_digit(digit_image("8"), TEMPLATES) is None


def test_blank_or_missing_templates_read_nothing():
    assert read_rank_digit(np.full((H, W, 3), 25, np.uint8), TEMPLATES) is None
    assert read_rank_digit(digit_image("3"), {}) is None
