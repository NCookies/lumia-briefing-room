"""라벨셋 대비 검출 정확도를 리포트한다. (plan.md §7)

지표: 교전 재현율/정밀도, 경계 오차, 분할/병합 횟수.
SPEC §5: "검출기는 테스트 하네스를 먼저 만든다"에 대응하는 실측 라벨셋 평가 도구.

labels.jsonl 한 줄:
    {"session_dir": "...", "match_start": "2026-09-19T13:07:47+00:00",
     "match_end": "2026-09-19T13:20:00+00:00", "combats": [[412.0, 447.0], ...]}

usage:
    python tools/eval_detect.py <labels.jsonl> [--ffmpeg PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lumia_briefing_room.config import discover_ffmpeg  # noqa: E402
from lumia_briefing_room.detect.match import detect_match  # noqa: E402
from lumia_briefing_room.video.segments import segment_time_range  # noqa: E402
from lumia_briefing_room.video.session import RecordingSession  # noqa: E402


@dataclass(frozen=True)
class EvalReport:
    recall: float
    precision: float
    mean_boundary_error: float
    splits: int
    merges: int
    matched_pairs: int
    ground_truth_count: int
    detected_count: int


def _overlaps(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] <= b[1] and a[1] >= b[0]


def evaluate_intervals(
    ground_truth: list[tuple[float, float]],
    detected: list[tuple[float, float]],
) -> EvalReport:
    """구간 단위로 겹침 기준 매칭해 재현율/정밀도/경계오차/분할/병합을 낸다."""
    gt_matches: list[list[int]] = [[] for _ in ground_truth]
    det_matches: list[list[int]] = [[] for _ in detected]

    for gi, g in enumerate(ground_truth):
        for di, d in enumerate(detected):
            if _overlaps(g, d):
                gt_matches[gi].append(di)
                det_matches[di].append(gi)

    matched_gt = sum(1 for m in gt_matches if m)
    matched_det = sum(1 for m in det_matches if m)

    recall = matched_gt / len(ground_truth) if ground_truth else 1.0
    precision = matched_det / len(detected) if detected else (1.0 if not ground_truth else 0.0)

    splits = sum(1 for m in gt_matches if len(m) > 1)
    merges = sum(1 for m in det_matches if len(m) > 1)

    boundary_errors = []
    for gi, dis in enumerate(gt_matches):
        if not dis:
            continue
        g = ground_truth[gi]
        best = min(dis, key=lambda di: abs(detected[di][0] - g[0]) + abs(detected[di][1] - g[1]))
        d = detected[best]
        boundary_errors.append((abs(d[0] - g[0]) + abs(d[1] - g[1])) / 2)

    mean_boundary_error = sum(boundary_errors) / len(boundary_errors) if boundary_errors else 0.0

    return EvalReport(
        recall=recall,
        precision=precision,
        mean_boundary_error=mean_boundary_error,
        splits=splits,
        merges=merges,
        matched_pairs=matched_gt,
        ground_truth_count=len(ground_truth),
        detected_count=len(detected),
    )


def _parse_utc(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def evaluate_labels(labels_path: Path, *, ffmpeg_path: Path) -> list[tuple[str, EvalReport]]:
    reports = []
    with open(labels_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            session = RecordingSession.load(Path(entry["session_dir"]))
            seg_range = segment_time_range(
                session, _parse_utc(entry["match_start"]), _parse_utc(entry["match_end"])
            )
            result = detect_match(session, seg_range, ffmpeg_path=ffmpeg_path)
            ground_truth = [tuple(c) for c in entry["combats"]]
            detected = [(iv.start, iv.end) for iv in result.intervals]
            reports.append((entry["session_dir"], evaluate_intervals(ground_truth, detected)))
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", type=Path)
    parser.add_argument("--ffmpeg", type=Path, default=None)
    args = parser.parse_args()

    ffmpeg_path = args.ffmpeg or discover_ffmpeg()
    if ffmpeg_path is None:
        raise SystemExit("ffmpeg 를 찾을 수 없다")

    reports = evaluate_labels(args.labels, ffmpeg_path=ffmpeg_path)
    for name, r in reports:
        print(
            f"{name}: recall={r.recall:.2f} precision={r.precision:.2f} "
            f"boundary_err={r.mean_boundary_error:.1f}s splits={r.splits} merges={r.merges}"
        )
    if reports:
        n = len(reports)
        avg_recall = sum(r.recall for _, r in reports) / n
        avg_precision = sum(r.precision for _, r in reports) / n
        print(f"평균: recall={avg_recall:.2f} precision={avg_precision:.2f}")


if __name__ == "__main__":
    main()
