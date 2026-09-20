from __future__ import annotations

import numpy as np

from lumia_briefing_room.detect.color import channel_stats

MINIMAP_ICON_MIN_PCT = 4.0
HP_GREEN_MIN_PCT = 0.5


def minimap_visible(header_rgb: np.ndarray) -> bool:
    """SPEC §2.12: 미니맵 헤더 우측의 밝은 회색 아이콘 4개가 보이는지."""
    stats = channel_stats(header_rgb)
    icons = (stats.v > 170) & (stats.s < 30)
    return float(icons.mean() * 100) >= MINIMAP_ICON_MIN_PCT


def hp_bar_visible(strip_rgb: np.ndarray) -> bool:
    """SPEC §2.12: 하단 중앙 띠에 내 체력바(초록)가 있는지."""
    stats = channel_stats(strip_rgb)
    green = (stats.g > 150) & (stats.g - stats.b > 70) & (stats.g - stats.r > 25)
    return float(green.mean() * 100) >= HP_GREEN_MIN_PCT


def read_spectating(header_rgb: np.ndarray, strip_rgb: np.ndarray) -> bool | None:
    """관전 중이면 True, 캐릭터 UI가 있으면 False, 미니맵도 없으면(암전·로비) None.

    사망 후 캐릭터 전용 UI(초상화·스킬바·체력바)가 사라지고 미니맵은 남는다.
    """
    if not minimap_visible(header_rgb):
        return None
    return not hp_bar_visible(strip_rgb)
