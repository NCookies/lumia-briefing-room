from __future__ import annotations

import numpy as np

IN_COMBAT_RED_MIN_PCT = 3.0
ORANGE_MIN_PCT = 2.0
GREEN_MAX_PCT = 0.5


def slot_is_dead(bar_rgb: np.ndarray) -> bool:
    """SPEC §2.12: 팀원 체력바가 주황(리스폰 대기)이고 초록이 없으면 사망.

    초상화 빨강은 캐릭터 머리색과 전투 중 빨간 링에 오염되어 못 쓴다. 바 색은 그림과 무관하다.
    """
    f = bar_rgb.astype(np.float32)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    orange = float(((r > 200) & (g > 100) & (g < 190) & (b < 90)).mean() * 100)
    green = float(((g > 170) & (r < 160) & (b < 120)).mean() * 100)
    return orange >= ORANGE_MIN_PCT and green < GREEN_MAX_PCT


def slot_in_combat(ring_rgb: np.ndarray) -> bool:
    """SPEC §2.12: 팀원이 전투 중이면 초상화 둘레 링이 빨갛게 변한다(내 배지와 같은 상태).

    평상시 링은 분홍/보라라 파랑 성분이 남는다. b < 0.45r 로 빨강만 센다.
    사망한 팀원의 얼굴도 빨갛게 덮이므로 combat_slots() 가 체력바로 따로 걸러낸다.
    """
    f = ring_rgb.astype(np.float32)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    red = (r > 110) & (g < 0.45 * r) & (b < 0.45 * r)
    return float(red.mean() * 100) >= IN_COMBAT_RED_MIN_PCT


def combat_slots(rings: list[np.ndarray], bars: list[np.ndarray]) -> list[int]:
    return [i for i, (ring, bar) in enumerate(zip(rings, bars)) if slot_in_combat(ring) and not slot_is_dead(bar)]


def dead_slots(bars: list[np.ndarray]) -> list[int]:
    return [i for i, bar in enumerate(bars) if slot_is_dead(bar)]


def new_deaths(series: list[tuple[float, list[int]]]) -> list[tuple[float, int]]:
    """샘플별 사망 슬롯 목록에서 '살아있다가 죽은' 순간만 (t, 슬롯) 으로 뽑는다.

    첫 샘플에 이미 죽어 있던 슬롯은 이 구간에서 벌어진 사건이 아니므로 제외한다.
    """
    events: list[tuple[float, int]] = []
    previous: set[int] | None = None
    for t, dead in series:
        current = set(dead)
        if previous is not None:
            events.extend((t, slot) for slot in sorted(current - previous))
        previous = current
    return events
