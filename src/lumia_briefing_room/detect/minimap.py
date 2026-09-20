from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

MIN_RADIUS = 7
MAX_RADIUS = 16
RING_MIN_PIXELS = 25
SAT_MIN = 110
VAL_MIN = 110
ALLY_HUE_MIN = 45
ALLY_HUE_MAX = 260


def _ring_hue(hsv: np.ndarray, gray_shape: tuple[int, int], x: int, y: int, r: int) -> int | None:
    mask = np.zeros(gray_shape, np.uint8)
    cv2.circle(mask, (x, y), r, 255, 2)
    px = hsv[mask > 0]
    px = px[(px[:, 1] > SAT_MIN) & (px[:, 2] > VAL_MIN)]
    if len(px) < RING_MIN_PIXELS:
        return None
    return int(np.median(px[:, 0])) * 2


@dataclass(frozen=True)
class RingCounts:
    enemy: int
    ally: int


def count_rings(minimap_rgb: np.ndarray) -> RingCounts:
    """SPEC §2.12: 미니맵의 원형 아이콘 링을 색으로 나눠 센다. 빨강 = 적, 노랑/초록/파랑 = 아군.

    배경 색 카운팅은 금지구역 빨강과 시야 원에 묻혀 못 쓴다. 원형 링을 먼저 찾고 테두리 색만 본다.
    아군에는 내 아이콘도 들어간다(내 아이콘 색은 매치마다 달라 따로 특정하지 않는다).
    """
    bgr = cv2.cvtColor(minimap_rgb, cv2.COLOR_RGB2BGR)
    gray = cv2.medianBlur(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), 3)
    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1, minDist=10,
        param1=100, param2=18, minRadius=MIN_RADIUS, maxRadius=MAX_RADIUS,
    )
    if circles is None:
        return RingCounts(0, 0)

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    enemy = ally = 0
    for x, y, r in np.uint16(np.around(circles))[0]:
        hue = _ring_hue(hsv, gray.shape, int(x), int(y), int(r))
        if hue is None:
            continue
        if hue < 15 or hue >= 345:
            enemy += 1
        elif ALLY_HUE_MIN <= hue < ALLY_HUE_MAX:
            ally += 1
    return RingCounts(enemy, ally)


def count_enemy_rings(minimap_rgb: np.ndarray) -> int:
    return count_rings(minimap_rgb).enemy
