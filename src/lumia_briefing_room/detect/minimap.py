from __future__ import annotations

import cv2
import numpy as np

MIN_RADIUS = 7
MAX_RADIUS = 16
RING_MIN_PIXELS = 25
SAT_MIN = 110
VAL_MIN = 110


def _ring_hue(hsv: np.ndarray, gray_shape: tuple[int, int], x: int, y: int, r: int) -> int | None:
    mask = np.zeros(gray_shape, np.uint8)
    cv2.circle(mask, (x, y), r, 255, 2)
    px = hsv[mask > 0]
    px = px[(px[:, 1] > SAT_MIN) & (px[:, 2] > VAL_MIN)]
    if len(px) < RING_MIN_PIXELS:
        return None
    return int(np.median(px[:, 0])) * 2


def count_enemy_rings(minimap_rgb: np.ndarray) -> int:
    """SPEC §2.12: 미니맵의 원형 아이콘 링 중 빨강(적)의 개수.

    배경 색 카운팅은 금지구역 빨강과 시야 원에 묻혀 못 쓴다. 원형 링을 먼저 찾고 테두리 색만 본다.
    노랑/초록/파랑은 아군이며, 내 아이콘 색은 매치마다 달라 아군으로 셀 필요가 없다.
    """
    bgr = cv2.cvtColor(minimap_rgb, cv2.COLOR_RGB2BGR)
    gray = cv2.medianBlur(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), 3)
    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1, minDist=10,
        param1=100, param2=18, minRadius=MIN_RADIUS, maxRadius=MAX_RADIUS,
    )
    if circles is None:
        return 0

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    enemies = 0
    for x, y, r in np.uint16(np.around(circles))[0]:
        hue = _ring_hue(hsv, gray.shape, int(x), int(y), int(r))
        if hue is not None and (hue < 15 or hue >= 345):
            enemies += 1
    return enemies
