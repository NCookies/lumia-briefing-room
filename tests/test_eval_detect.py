import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from eval_detect import EvalReport, evaluate_intervals  # noqa: E402


def test_perfect_match():
    gt = [(0.0, 10.0), (20.0, 30.0)]
    det = [(0.0, 10.0), (20.0, 30.0)]
    report = evaluate_intervals(gt, det)
    assert report.recall == 1.0
    assert report.precision == 1.0
    assert report.mean_boundary_error == 0.0
    assert report.splits == 0
    assert report.merges == 0


def test_missed_ground_truth_lowers_recall():
    gt = [(0.0, 10.0), (20.0, 30.0)]
    det = [(0.0, 10.0)]
    report = evaluate_intervals(gt, det)
    assert report.recall == 0.5
    assert report.precision == 1.0


def test_false_positive_lowers_precision():
    gt = [(0.0, 10.0)]
    det = [(0.0, 10.0), (50.0, 60.0)]
    report = evaluate_intervals(gt, det)
    assert report.recall == 1.0
    assert report.precision == 0.5


def test_split_detected_as_multiple_intervals():
    gt = [(0.0, 20.0)]
    det = [(0.0, 8.0), (12.0, 20.0)]
    report = evaluate_intervals(gt, det)
    assert report.splits == 1
    assert report.recall == 1.0


def test_merge_of_two_ground_truth_into_one_detection():
    gt = [(0.0, 8.0), (12.0, 20.0)]
    det = [(0.0, 20.0)]
    report = evaluate_intervals(gt, det)
    assert report.merges == 1
    assert report.recall == 1.0


def test_boundary_error_measures_offset():
    gt = [(10.0, 20.0)]
    det = [(13.0, 20.0)]  # 시작이 3초 늦게 잡힘
    report = evaluate_intervals(gt, det)
    assert report.mean_boundary_error == 1.5  # (|13-10| + |20-20|) / 2


def test_empty_ground_truth_and_detection_is_perfect():
    report = evaluate_intervals([], [])
    assert report.recall == 1.0
    assert report.precision == 1.0


def test_empty_ground_truth_with_detections_has_zero_precision():
    report = evaluate_intervals([], [(0.0, 5.0)])
    assert report.precision == 0.0


def test_ground_truth_with_no_detections_has_zero_recall():
    report = evaluate_intervals([(0.0, 5.0)], [])
    assert report.recall == 0.0


def test_eval_report_is_frozen():
    report = EvalReport(
        recall=1.0, precision=1.0, mean_boundary_error=0.0,
        splits=0, merges=0, matched_pairs=0, ground_truth_count=0, detected_count=0,
    )
    import pytest
    with pytest.raises(Exception):
        report.recall = 0.5  # type: ignore[misc]
