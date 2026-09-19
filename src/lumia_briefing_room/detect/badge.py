from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lumia_briefing_room.detect.color import channel_stats, count, vivid_mask

V_MIN = 90
S_MIN = 60
ORANGE_MIN = 100
PRESENT_MIN = 250


@dataclass(frozen=True)
class BadgeColorCounts:
    orange: int
    yellow: int
    blue: int


def classify_badge(rgb: np.ndarray) -> BadgeColorCounts:
    """SPEC §2.7: 배지 ROI의 선명한 픽셀을 색 계열별로 센다.

    주황 = V≥90 AND S≥60 AND R>B+60 AND R≥G AND G<R*0.80  (교전 중)
    노랑 = V≥90 AND S≥60 AND R>B+60 AND G≥R*0.80          (평상시, 노랑 배지)
    파랑 = V≥90 AND S≥60 AND B>R+40                        (평상시, 파랑 배지)
    """
    stats = channel_stats(rgb)
    vivid = vivid_mask(stats, v_min=V_MIN, s_min=S_MIN)
    warm = vivid & (stats.r > stats.b + 60)
    orange = warm & (stats.r >= stats.g) & (stats.g < stats.r * 0.80)
    yellow = warm & (stats.g >= stats.r * 0.80)
    blue = vivid & (stats.b > stats.r + 40)
    return BadgeColorCounts(orange=count(orange), yellow=count(yellow), blue=count(blue))


def read_badge(rgb: np.ndarray) -> bool | None:
    """교전 중이면 True, 평상시면 False, 배지가 안 보이면(로비/암전) None."""
    counts = classify_badge(rgb)
    total = counts.orange + counts.yellow + counts.blue
    if total < PRESENT_MIN:
        return None
    return counts.orange >= ORANGE_MIN
