"""사용자가 UI 에서 찍은 교전/사냥 라벨로 pvpScore 를 평가한다. (plan-pvp 4단계 튜닝 루프)

usage:
    python tools/eval_pvp.py [clips_dir]

확인하는 것:
  1. 확정 증거(점수 1.0)가 있는데 사용자가 '사냥'이라 한 클립 — 검출기 오탐이다.
  2. 확정 증거가 없는 클립에서 적 링 평균이 교전/사냥을 가르는지 (SPEC §2.12 의 핵심 질문).
  3. 임계별 정밀도/재현율. 겹치면 이 신호는 버린다.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def load_clips(clips_dir: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(clips_dir.glob("*.json"))]


def _ring_stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
        "min": min(values),
        "max": max(values),
    }


def evaluate_labels(clips: list[dict]) -> dict:
    labeled = [c for c in clips if c.get("userLabel") in ("pvp", "pve")]
    pvp = [c for c in labeled if c["userLabel"] == "pvp"]
    pve = [c for c in labeled if c["userLabel"] == "pve"]

    def score(c: dict) -> float:
        return c.get("pvpScore") or 0.0

    def rings(group: list[dict]) -> list[float]:
        return [
            c["enemyRingMean"] for c in group
            if score(c) < 1.0 and c.get("enemyRingMean") is not None
        ]

    sweep = []
    for threshold in sorted({score(c) for c in labeled if score(c) > 0}):
        tp = sum(1 for c in pvp if score(c) >= threshold)
        fp = sum(1 for c in pve if score(c) >= threshold)
        fn = len(pvp) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        sweep.append(
            {"threshold": threshold, "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}
        )

    best = max(sweep, key=lambda r: (r["f1"], r["threshold"])) if sweep else None
    return {
        "labeled": len(labeled),
        "pvp": len(pvp),
        "pve": len(pve),
        "confirmed_but_pve": sum(1 for c in pve if score(c) >= 1.0),
        "rings": {"pvp": _ring_stats(rings(pvp)), "pve": _ring_stats(rings(pve))},
        "sweep": sweep,
        "best": best,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clips_dir", nargs="?", type=Path, default=Path.home() / "Videos/LumiaBriefingRoom/clips")
    report = evaluate_labels(load_clips(parser.parse_args().clips_dir))

    print(f"라벨 {report['labeled']}개 (교전 {report['pvp']} / 사냥 {report['pve']})")
    if report["confirmed_but_pve"]:
        print(f"⚠ 확정 증거가 있는데 사냥이라 라벨된 클립 {report['confirmed_but_pve']}개 — 검출기 오탐 확인 필요")
    for name in ("pvp", "pve"):
        r = report["rings"][name]
        print(f"확정 증거 없는 {name} 의 적 링 평균: n={r['n']} 평균={r['mean']} 중앙={r['median']} 범위={r['min']}~{r['max']}")
    for row in report["sweep"]:
        print(f"  임계 {row['threshold']:.2f}: 정밀도 {row['precision']:.2f} 재현율 {row['recall']:.2f} F1 {row['f1']:.2f}")
    if report["best"]:
        print("최적 임계:", report["best"])


if __name__ == "__main__":
    main()
