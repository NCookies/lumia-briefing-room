from __future__ import annotations

import numpy as np

from lumia_briefing_room.detect.color import channel_stats

BLUE_MIN = 120
BLUE_OVER_RED = 20

# SPEC §2.12 #9, plan-pvp.md §2.8-b: 라벨 110개(pvp 73 / pve 37)로 검증.
# 클립 안에서 이 값의 최솟값 대비 최댓값 차이(delta)가 이 임계를 넘으면 궁을 쓴 것으로 본다.
# AUC(delta) = 0.914 (pvp 90% 검출, pve 27% 검출) — scripts/probe/eval_ultimate_signal.py.
DELTA_THRESHOLD = 0.15

# 2026-09-23 실사용 오탐 2건으로 발견: W/E/R 스킬을 아직 안 찍으면 아이콘이 빨간 X 로
# 덮인 "잠김" 상태(어둡고 채도 낮음)다. 교전 중 레벨업해서 스킬을 찍는 순간 원래 색
# "해금" 아이콘으로 바뀌는데, 이 전환이 blue_tint_ratio 델타 계산에서 진짜 쿨타임
# 진입과 구분이 안 됐다(해금된 아이콘 원화가 파르스름한 캐릭터는 특히 심함).
# 실측(2026-09-23, 캐릭터 2명 - MARTIN·BIHYUN): 잠김 상태의 빨간 X 오버레이는
# ROI 픽셀의 5.4~5.5% 를 차지하고(캐릭터 무관, 오버레이 자체가 고정 그래픽이라 일관됨),
# 동시에 어둡다(v_median 36~40). 해금 상태는 원화가 밝든 어둡든(캐릭터마다 다름) 이
# 조합을 만족하지 않았다 — 불이나 빨간 계열 원화(BIHYUN 해금 상태)는 red_frac 이
# 0.30 으로 훨씬 높고, 어두운 원화(CHIAR 해금 상태)는 red_frac 이 0(빨강 자체가 없음).
LOCKED_RED_MIN = 120
LOCKED_RED_OVER_OTHERS = 40
LOCKED_RED_FRAC_RANGE = (0.02, 0.15)
LOCKED_VALUE_MAX = 55


def _red_x_fraction(rgb: np.ndarray) -> float:
    a = rgb.astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    red = (r > LOCKED_RED_MIN) & (r > g + LOCKED_RED_OVER_OTHERS) & (r > b + LOCKED_RED_OVER_OTHERS)
    return float(red.mean())


def is_locked(rgb: np.ndarray) -> bool:
    """스킬 포인트를 아직 안 찍어 R 아이콘이 빨간 X 로 덮인 "잠김" 상태인가.

    표본이 아직 2캐릭터뿐이라(실측 노트 위 참고) 더 라벨이 쌓이면 재검증이 필요하다.
    """
    lo, hi = LOCKED_RED_FRAC_RANGE
    red_frac = _red_x_fraction(rgb)
    if not (lo <= red_frac <= hi):
        return False
    value = rgb.astype(np.int16).max(axis=-1)
    return bool(np.median(value) < LOCKED_VALUE_MAX)


def max_rise(values: list[float]) -> float:
    """values(시간순)에서 이전의 더 낮은 지점 대비 이후 지점이 얼마나 올랐는지의 최댓값.

    단순 최댓값-최솟값 범위(range)와 다르다 - range 는 시간 순서를 안 보므로, 클립이
    시작될 때 이미 직전 교전에서 쓴 궁의 쿨타임이 돌고 있다가 시간이 지나며 되돌아오기만
    하는 경우까지 "많이 변했다"고 잘못 판단한다(2026-09-23 실사용 오탐: 연구소 버니스·
    묘지 마르티나 클립에 궁을 안 썼는데 근거로 잡힘 - 값이 시종일관 단조 감소했을 뿐).
    상승분만 보면 이런 순수 감소 구간은 0에 가깝게 나온다. "최저점 매수 후 최고점 매도"
    와 같은 계산이다.
    """
    if len(values) < 2:
        return 0.0
    best = 0.0
    running_min = values[0]
    for v in values[1:]:
        best = max(best, v - running_min)
        running_min = min(running_min, v)
    return best


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
