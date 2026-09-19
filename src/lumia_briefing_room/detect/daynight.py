from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lumia_briefing_room.detect.color import channel_stats, count, vivid_mask

V_MIN = 90
S_MIN = 55
MIN_ICON_PX = 100


@dataclass(frozen=True)
class DayNightCounts:
    yellow: int
    purple: int


def classify_day_night(rgb: np.ndarray) -> DayNightCounts:
    """SPEC §2.10: 상단 낮/밤 아이콘의 선명한 픽셀을 색 계열별로 센다.

    노랑 = V≥90 AND S≥55 AND R>B+50 AND G>B+30  (해)
    보라 = V≥90 AND S≥55 AND B>G+40 AND R>G+20  (달)
    """
    stats = channel_stats(rgb)
    vivid = vivid_mask(stats, v_min=V_MIN, s_min=S_MIN)
    yellow = vivid & (stats.r > stats.b + 50) & (stats.g > stats.b + 30)
    purple = vivid & (stats.b > stats.g + 40) & (stats.r > stats.g + 20)
    return DayNightCounts(yellow=count(yellow), purple=count(purple))


def read_day_night(rgb: np.ndarray) -> str | None:
    """낮이면 "day", 밤이면 "night", 아이콘이 안 보이면 None.

    research §4.9: 상단 바가 반투명이라 배경이 섞인다. 단순 임계가 아니라
    "노랑과 보라 중 큰 쪽"으로 판정해야 배경 간섭을 이긴다.
    """
    counts = classify_day_night(rgb)
    if max(counts.yellow, counts.purple) < MIN_ICON_PX:
        return None
    return "day" if counts.yellow > counts.purple else "night"
