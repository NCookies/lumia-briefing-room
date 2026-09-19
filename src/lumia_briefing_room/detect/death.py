from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lumia_briefing_room.detect.color import channel_stats
from lumia_briefing_room.detect.intervals import to_intervals

DEATH_VALUE_RATIO = 0.6
DEATH_SAT_RATIO = 0.7


@dataclass(frozen=True)
class FaceStat:
    t: float
    value: float
    sat: float


def face_stat(rgb: np.ndarray, t: float) -> FaceStat:
    stats = channel_stats(rgb)
    return FaceStat(t=t, value=float(stats.v.mean()), sat=float(stats.s.mean()))


def _is_dead_sample(
    value: float, sat: float, base_value: float, base_sat: float,
    *, value_ratio: float, sat_ratio: float,
) -> bool:
    return value <= base_value * value_ratio and sat <= base_sat * sat_ratio


def detect_death(
    stats: list[FaceStat],
    *,
    value_ratio: float = DEATH_VALUE_RATIO,
    sat_ratio: float = DEATH_SAT_RATIO,
) -> list[tuple[float, float]]:
    """research §4.7: 사망하면 초상화 채도가 절반, 밝기가 1/3로 떨어진다.

    절대 임계 대신 그 매치의 평소(중앙값) 대비 상대 하락을 본다 —
    밤 맵/실내에서는 평상시 밝기도 크게 떨어지기 때문(SPEC §2.7).
    """
    if not stats:
        return []

    base_value = float(np.median([s.value for s in stats]))
    base_sat = float(np.median([s.sat for s in stats]))
    if base_value <= 0 or base_sat <= 0:
        return []

    states: list[tuple[float, bool | None]] = [
        (
            s.t,
            _is_dead_sample(
                s.value, s.sat, base_value, base_sat,
                value_ratio=value_ratio, sat_ratio=sat_ratio,
            ),
        )
        for s in stats
    ]
    return to_intervals(states)
