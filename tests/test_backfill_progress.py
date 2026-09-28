import pytest

from lumia_briefing_room.pipeline.backfill_progress import (
    DEFAULT_AVG_GAME_SEC,
    DEFAULT_GAME_LENGTH_SEC,
    AdaptiveGameDuration,
    MonotonicProgress,
    Workload,
    analysis_workload_sec,
    compute_workload,
    estimate_game_count,
    overall_fraction,
    scan_workload_sec,
)


def test_estimate_game_count_scales_with_video_length():
    assert estimate_game_count(0.0) == 0.0
    assert estimate_game_count(DEFAULT_GAME_LENGTH_SEC) == 1.0
    assert estimate_game_count(DEFAULT_GAME_LENGTH_SEC * 9) == 9.0


def test_estimate_game_count_never_negative():
    assert estimate_game_count(-100.0) == 0.0


def test_scan_workload_sec_divides_by_speedup():
    assert scan_workload_sec(2500.0, speedup=25.0) == 100.0
    assert scan_workload_sec(2500.0, speedup=0.0) == 0.0


def test_analysis_workload_sec_multiplies_game_count_by_average():
    assert analysis_workload_sec(9.0, avg_game_sec=80.0) == 720.0
    assert analysis_workload_sec(-1.0, avg_game_sec=80.0) == 0.0


def test_compute_workload_combines_scan_and_analysis():
    workload = compute_workload(video_seconds=2500.0, speedup=25.0, game_count=9.0, avg_game_sec=80.0)

    assert workload.scan_sec == 100.0
    assert workload.analysis_sec == 720.0
    assert workload.total_sec == 820.0


def test_overall_fraction_is_zero_at_start_and_one_when_done():
    workload = Workload(scan_sec=100.0, analysis_sec=700.0)

    assert overall_fraction(0.0, workload) == 0.0
    assert overall_fraction(800.0, workload) == 1.0


def test_overall_fraction_clamped_to_one_even_if_elapsed_overshoots():
    workload = Workload(scan_sec=100.0, analysis_sec=700.0)

    assert overall_fraction(10_000.0, workload) == 1.0


def test_overall_fraction_is_zero_when_workload_is_empty():
    assert overall_fraction(50.0, Workload(scan_sec=0.0, analysis_sec=0.0)) == 0.0


def test_overall_fraction_increases_monotonically_as_elapsed_grows_within_a_run():
    workload = Workload(scan_sec=200.0, analysis_sec=800.0)
    fractions = [overall_fraction(t, workload) for t in (0, 100, 200, 400, 600, 800, 1000)]

    assert fractions == sorted(fractions)
    assert fractions[0] == 0.0
    assert fractions[-1] == 1.0


class TestMonotonicProgress:
    def test_starts_at_floor(self):
        assert MonotonicProgress(floor=0.1).value == pytest.approx(0.1)
        assert MonotonicProgress().value == 0.0

    def test_pushing_a_higher_value_updates_it(self):
        m = MonotonicProgress()
        assert m.push(0.3) == pytest.approx(0.3)
        assert m.push(0.5) == pytest.approx(0.5)

    def test_pushing_a_lower_value_keeps_the_previous_maximum(self):
        """스캔이 끝난 뒤 실제 게임 수로 다시 계산해서 값이 줄어도 화면은 뒤로 가지 않는다."""
        m = MonotonicProgress()
        m.push(0.5)

        assert m.push(0.3) == pytest.approx(0.5)
        assert m.push(0.6) == pytest.approx(0.6)

    def test_clamps_to_0_1_range(self):
        m = MonotonicProgress()
        assert m.push(-1.0) == 0.0
        assert m.push(2.0) == 1.0

    def test_recompute_scenario_stays_non_decreasing_across_the_whole_sequence(self):
        """스캔 중 게임 수를 적게 추정했다가(작업량 과소평가) 스캔이 끝나 실제 게임 수로 재계산하면
        분모가 커져 계산값이 순간적으로 줄어들 수 있다 — 화면에 보이는 값은 그래도 단조 증가해야 한다."""
        # 스캔 전: 세션 길이로 게임 3개를 추정
        early_workload = compute_workload(video_seconds=1000.0, speedup=25.0, game_count=3.0)
        raw_early = [
            overall_fraction(t, early_workload) for t in (0, 10, 20, 30, 40)
        ]
        # 스캔이 끝나 실제로는 게임이 9개였다(작업량이 커짐 → 순간 계산값이 내려갈 수 있음)
        late_workload = compute_workload(video_seconds=1000.0, speedup=25.0, game_count=9.0)
        raw_late = [
            overall_fraction(early_workload.scan_sec + t, late_workload) for t in (0, 80, 160)
        ]

        m = MonotonicProgress()
        displayed = [m.push(v) for v in raw_early + raw_late]

        assert displayed == sorted(displayed)
        # 재계산 직후 원값은 실제로 떨어졌는지(문제 상황 재현) 확인
        assert raw_late[0] < raw_early[-1]


class TestAdaptiveGameDuration:
    def test_uses_the_constant_until_something_is_recorded(self):
        adaptive = AdaptiveGameDuration()

        assert adaptive.estimate == DEFAULT_AVG_GAME_SEC

    def test_uses_the_average_of_recorded_durations(self):
        adaptive = AdaptiveGameDuration()
        adaptive.record(60.0)
        adaptive.record(100.0)

        assert adaptive.estimate == pytest.approx(80.0)

    def test_only_keeps_a_rolling_window(self):
        adaptive = AdaptiveGameDuration(window=3)
        for d in (60.0, 60.0, 60.0, 120.0, 120.0, 120.0):
            adaptive.record(d)

        assert adaptive.estimate == pytest.approx(120.0)

    def test_ignores_non_positive_durations(self):
        adaptive = AdaptiveGameDuration()
        adaptive.record(0.0)
        adaptive.record(-5.0)

        assert adaptive.estimate == DEFAULT_AVG_GAME_SEC
