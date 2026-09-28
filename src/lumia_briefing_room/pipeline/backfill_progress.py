"""B8: 진행률을 "예상 작업 시간" 비율로 계산하는 순수 로직. (plan-backfill.md §0 B8)

지금까지는 스캔을 0~50%, 게임 분석을 50~100% 로 고정 반반 나눴다. 실측(§4)은 스캔이
28배속인데 게임 분석은 게임당 60~100초라 게임이 여러 개면 스캔은 전체의 20% 안팎이라,
스캔이 끝나자마자 50% 가 됐다가 그 뒤로 거의 안 움직이는 것처럼 보였다.

여기서는 그 대신 "각 단계가 걸릴 것으로 보이는 시간(초)" 을 작업량으로 삼아 비율을 계산한다.
스캔이 끝나기 전에는 게임 수를 몰라 세션 길이로 거칠게 추정하고, 스캔이 끝나 실제 게임 수를 알면
작업량을 다시 계산한다 — 이때 계산값이 순간적으로 줄어들 수 있어(작업량 분모가 커지므로) 화면에
보여주는 값은 `MonotonicProgress` 로 단조 증가만 하게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass

# 실측(plan-backfill.md §4): 게임당 60~100초. 중앙값을 시작값으로 쓰고, 실행 중 실제로 걸린
# 시간이 쌓이면 AdaptiveGameDuration 이 이동 평균으로 보정한다(§7 확인 필요 1번 답).
DEFAULT_AVG_GAME_SEC = 80.0

# 실측(plan-backfill.md §2, 2세션 약 130분 분량, 경기 5판 처리 포함 292초)의 약 27배속에서
# 여유를 둔 값. 다른 PC 는 다를 수 있어 안내에는 "대략"이라고 쓴다.
DEFAULT_SCAN_SPEEDUP = 25.0

# 스캔이 끝나기 전, 세션 길이로 게임 수를 거칠게 추정할 때 쓰는 평균 경기 길이(로비 포함).
# B0 실측(§2, 8~23분)과 다시보기 실측(plan-vod.md, 로비 포함 20~30분권)을 절충한 값이다.
# 실제 분포(솔로/듀오/스쿼드, 대기 시간)를 모으기 전까지는 근사치라는 한계가 있다(§7 확인 필요 2번 답).
DEFAULT_GAME_LENGTH_SEC = 20 * 60.0


def estimate_game_count(video_seconds: float, avg_game_length_sec: float = DEFAULT_GAME_LENGTH_SEC) -> float:
    """스캔이 끝나기 전, 세션 길이만으로 게임 수를 거칠게 추정한다."""
    if avg_game_length_sec <= 0 or video_seconds <= 0:
        return 0.0
    return video_seconds / avg_game_length_sec


@dataclass(frozen=True)
class Workload:
    scan_sec: float
    analysis_sec: float

    @property
    def total_sec(self) -> float:
        return self.scan_sec + self.analysis_sec


def scan_workload_sec(video_seconds: float, speedup: float) -> float:
    """스캔 작업량(초) = 스캔할 세션 길이 ÷ 스캔 배속."""
    if speedup <= 0:
        return 0.0
    return max(0.0, video_seconds) / speedup


def analysis_workload_sec(game_count: float, avg_game_sec: float = DEFAULT_AVG_GAME_SEC) -> float:
    """분석 작업량(초) = 게임 수 × 게임당 평균 처리 시간."""
    return max(0.0, game_count) * max(0.0, avg_game_sec)


def compute_workload(
    *, video_seconds: float, speedup: float, game_count: float, avg_game_sec: float = DEFAULT_AVG_GAME_SEC
) -> Workload:
    return Workload(
        scan_sec=scan_workload_sec(video_seconds, speedup),
        analysis_sec=analysis_workload_sec(game_count, avg_game_sec),
    )


def overall_fraction(elapsed_sec: float, workload: Workload) -> float:
    """지금까지 한 일(초 환산) ÷ 전체 작업량. 작업량이 0 이면(대상 없음) 0."""
    total = workload.total_sec
    if total <= 0:
        return 0.0
    return min(1.0, max(0.0, elapsed_sec / total))


class MonotonicProgress:
    """재계산으로 계산값이 줄어도 화면에 보여주는 값은 뒤로 가지 않는다(단조 증가)."""

    def __init__(self, floor: float = 0.0) -> None:
        self._max = max(0.0, min(1.0, floor))

    @property
    def value(self) -> float:
        return self._max

    def push(self, value: float) -> float:
        clamped = max(0.0, min(1.0, value))
        if clamped > self._max:
            self._max = clamped
        return self._max


class AdaptiveGameDuration:
    """게임당 평균 처리 시간을 이번 실행에서 실제로 걸린 시간의 이동 평균으로 보정한다.

    표본이 없으면(막 시작했을 때) 기본값(실측 60~100초의 중앙값)을 쓰고, 게임을 처리할 때마다
    `record()` 로 실제 걸린 시간을 쌓아 최근 `window` 개의 평균으로 다음 게임의 남은 시간을 추정한다.
    다른 PC 는 사양이 다를 수 있다는 문제(§7 확인 필요 1번)를 이렇게 완화한다 — PC 마다 값이 스스로 맞춰진다.
    """

    def __init__(self, initial: float = DEFAULT_AVG_GAME_SEC, window: int = 5) -> None:
        self._initial = initial
        self._window = max(1, window)
        self._durations: list[float] = []

    @property
    def estimate(self) -> float:
        if not self._durations:
            return self._initial
        recent = self._durations[-self._window :]
        return sum(recent) / len(recent)

    def record(self, duration_sec: float) -> None:
        if duration_sec > 0:
            self._durations.append(duration_sec)
