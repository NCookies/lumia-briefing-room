"""옛 클립에 찍은 교전/사냥 라벨을, 시간이 겹치는 새 클립으로 옮긴다.

usage:
    python tools/migrate_labels.py <old_clips_dir> <new_clips_dir>

클립 경계가 바뀌면(예: 팀원 전투를 교전 신호로 추가) 클립 ID·구간이 달라져 라벨이 어긋난다.
새 클립이 옛 클립과 (같은 녹화 세션에서) 겹치면 라벨을 옮긴다:
  - 겹치는 라벨된 옛 클립 중 하나라도 pvp 면 pvp (기준: 클립에 교전이 *포함*되면 교전)
  - 전부 pve 면 pve
  - pvp 와 pve 가 섞이면 pvp 로 옮기되 labelConflict=True 로 표시해 사용자가 확인하게 한다
사용자가 새 클립에 이미 직접 찍은 라벨(labelSource=user)은 덮어쓰지 않는다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lumia_briefing_room.pipeline.label_migrate import load_metas, migrate_label, migrate_labels  # noqa: E402,F401


def migrate_folder(old_dir: Path, new_dir: Path) -> dict[str, int]:
    return migrate_labels(load_metas(sorted(old_dir.glob("*.json"))), sorted(new_dir.glob("*.json")))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_dir", type=Path)
    parser.add_argument("new_dir", type=Path)
    args = parser.parse_args()
    report = migrate_folder(args.old_dir, args.new_dir)
    print(
        f"이관 {report['migrated']}개 (그중 확인 필요 {report['conflicts']}개), "
        f"이미 직접 찍은 라벨 {report['skipped_user_labeled']}개는 건드리지 않음, "
        f"옮길 라벨이 없는 클립 {report['unlabeled']}개"
    )


if __name__ == "__main__":
    main()
