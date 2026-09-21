from __future__ import annotations

import cv2
import numpy as np

from lumia_briefing_room.detect.day import white_score
from lumia_briefing_room.detect.glyph import similarity

MIN_INK = 0.05
MIN_SIMILARITY = 0.85
CELL_SIZE = (12, 24)
DIGIT_STARTS = (0.05, 0.225, 0.6125, 0.7875)
CELL_WIDTH = 0.1625


def read_clock_zero(timer_rgb: np.ndarray) -> bool | None:
    """상단 게임 시계가 `00 : 00` 이면 True, 시계가 돌고 있으면 False, 시계가 안 보이면 None.

    다른 유저의 접속을 기다리는 대기방에서는 시계가 00:00 에 멈춰 있다. 네 자리가 전부 같은 모양(0)이므로
    본보기 없이 네 칸이 서로 닮았는지만 본다. 낮·밤 시계는 분의 십의 자리가 항상 0 이라 00:00 말고는 네 칸이 같을 수 없다.
    """
    score = white_score(timer_rgb)
    width = score.shape[1]
    cell_w = max(1, int(CELL_WIDTH * width))
    cells = [
        cv2.resize(score[:, int(a * width) : int(a * width) + cell_w], CELL_SIZE) for a in DIGIT_STARTS
    ]
    if min(float(c.mean()) for c in cells) < MIN_INK:
        return None
    return min(similarity(cells[0], c) for c in cells[1:]) >= MIN_SIMILARITY
