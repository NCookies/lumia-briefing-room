"""옛 클립에 찍은 교전/사냥 라벨을, 시간이 겹치는 새 클립으로 옮긴다.

클립 경계가 바뀌면(검출기 수정 후 다시 분석 등) 클립 ID·구간이 달라져 라벨이 어긋난다.
새 클립이 옛 클립과 (같은 녹화 세션에서) 겹치면 라벨을 옮긴다:
  - 겹치는 라벨된 옛 클립 중 하나라도 pvp 면 pvp (기준: 클립에 교전이 *포함*되면 교전)
  - 전부 pve 면 pve
  - pvp 와 pve 가 섞이면 pvp 로 옮기되 labelConflict=True 로 표시해 사용자가 확인하게 한다
사용자가 새 클립에 이미 직접 찍은 라벨(labelSource=user)은 덮어쓰지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

MIN_OVERLAP_SEC = 3.0


def _overlap(a: dict, b: dict) -> float:
    a0, a1 = a["videoOffsetSec"], a["videoOffsetSec"] + a["durationSec"]
    b0, b1 = b["videoOffsetSec"], b["videoOffsetSec"] + b["durationSec"]
    return max(0.0, min(a1, b1) - max(a0, b0))


def migrate_label(new: dict, olds: list[dict]) -> tuple[str | None, bool, list[str]]:
    hits = [
        o for o in olds
        if o.get("userLabel") and o["sessionDir"] == new["sessionDir"] and _overlap(new, o) >= MIN_OVERLAP_SEC
    ]
    if not hits:
        return None, False, []
    labels = {o["userLabel"] for o in hits}
    label = "pvp" if "pvp" in labels else "pve"
    return label, len(labels) > 1, [o["id"] for o in hits]


def load_metas(paths: list[Path]) -> list[dict]:
    clips = []
    for path in paths:
        meta = json.loads(path.read_text(encoding="utf-8"))
        meta["id"] = path.stem
        clips.append(meta)
    return clips


def migrate_labels(olds: list[dict], new_paths: list[Path]) -> dict[str, int]:
    report = {"migrated": 0, "conflicts": 0, "skipped_user_labeled": 0, "unlabeled": 0}
    for path in new_paths:
        fresh = json.loads(path.read_text(encoding="utf-8"))
        if fresh.get("userLabel") and fresh.get("labelSource") == "user":
            report["skipped_user_labeled"] += 1
            continue
        label, conflict, _ = migrate_label({**fresh, "id": path.stem}, olds)
        if label is None:
            report["unlabeled"] += 1
            continue
        fresh.update({"userLabel": label, "labelSource": "migrated", "labelConflict": conflict})
        path.write_text(json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8")
        report["migrated"] += 1
        report["conflicts"] += int(conflict)
    return report
