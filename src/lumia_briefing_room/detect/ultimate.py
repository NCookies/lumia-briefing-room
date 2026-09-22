from __future__ import annotations

import numpy as np

from lumia_briefing_room.detect.color import channel_stats

BLUE_MIN = 120
BLUE_OVER_RED = 20

# SPEC §2.12 #9, plan-pvp.md §2.8-b: 라벨 110개(pvp 73 / pve 37)로 검증.
# 클립 안에서 이 값의 최솟값 대비 최댓값 차이(delta)가 이 임계를 넘으면 궁을 쓴 것으로 본다.
# AUC(delta) = 0.914 (pvp 90% 검출, pve 27% 검출) — scripts/probe/eval_ultimate_signal.py.
DELTA_THRESHOLD = 0.15


def blue_tint_ratio(rgb: np.ndarray) -> float:
    """R(궁극기) 칸에서 쿨타임 오버레이의 파르스름한 픽셀 비율을 잰다.

    준비 상태는 원래 아이콘 색 그대로, 쿨타임 상태는 파르스름한 반투명 오버레이 +
    흰 숫자가 덮인다(육안 확인, 2026-09-22). **절대 임계로는 못 쓴다** — 캐릭터마다
    R 아이콘 원화 자체의 파란기 베이스라인이 달라서, 궁을 안 써도 이 값이 항상
    ~0.25 근방인 캐릭터가 있었다(라벨 110개 검증에서 드러남). 그래서 이 함수는
    비율만 반환하고, 판정은 클립 구간 안에서의 상승폭(delta)으로 한다
    (detect/match.py finalize_match, DELTA_THRESHOLD).
    """
    stats = channel_stats(rgb)
    blue_tint = (stats.b > BLUE_MIN) & (stats.b > stats.r + BLUE_OVER_RED)
    return float(blue_tint.mean())
