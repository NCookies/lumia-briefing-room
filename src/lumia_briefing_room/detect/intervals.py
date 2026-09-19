from __future__ import annotations

GAP_FILL_SAMPLES = 2
MIN_COMBAT_SAMPLES = 2


def to_intervals(
    states: list[tuple[float, bool | None]],
    *,
    gap_fill_samples: int = GAP_FILL_SAMPLES,
    min_combat_samples: int = MIN_COMBAT_SAMPLES,
) -> list[tuple[float, float]]:
    """배지 on/off 시계열을 교전 구간으로 만든다. (plan.md §5.3)

    규칙:
      1) None(판독 불가)은 직전 상태를 그대로 잇는다 — 교전 종료로 치지 않는다
      2) 양쪽이 True 이고 길이가 gap_fill_samples 이하인 False 구간은 메운다
      3) 길이가 min_combat_samples 미만인 True 구간은 버린다
      4) 구간 경계는 샘플 시각 그대로 사용한다
    """
    if not states:
        return []

    times = [t for t, _ in states]
    filled: list[bool] = []
    last = False
    for _, v in states:
        if v is not None:
            last = v
        filled.append(last)

    n = len(filled)

    i = 0
    while i < n:
        if not filled[i]:
            j = i
            while j < n and not filled[j]:
                j += 1
            has_before = i > 0 and filled[i - 1]
            has_after = j < n and filled[j]
            if has_before and has_after and (j - i) <= gap_fill_samples:
                for k in range(i, j):
                    filled[k] = True
            i = j
        else:
            i += 1

    i = 0
    while i < n:
        if filled[i]:
            j = i
            while j < n and filled[j]:
                j += 1
            if (j - i) < min_combat_samples:
                for k in range(i, j):
                    filled[k] = False
            i = j
        else:
            i += 1

    intervals: list[tuple[float, float]] = []
    i = 0
    while i < n:
        if filled[i]:
            j = i
            while j < n and filled[j]:
                j += 1
            intervals.append((times[i], times[j - 1]))
            i = j
        else:
            i += 1
    return intervals
