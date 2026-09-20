"""저장된 클립 메타데이터의 pvpScore/pvpSignals 를 재검출 없이 다시 계산한다.

usage:
    python tools/rescore_clips.py [clips_dir]

가중치를 바꿨거나 점수 규칙을 고쳤을 때 쓴다. 검출 결과(killDelta, died, 태그, enemyRingMean)는
메타데이터에 이미 있으므로 영상을 다시 분석하지 않는다. 사용자 라벨은 건드리지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lumia_briefing_room.config import FilterConfig  # noqa: E402
from lumia_briefing_room.detect.pvp import score_interval  # noqa: E402
from lumia_briefing_room.detect.types import CombatInterval  # noqa: E402


def rescore_meta(meta: dict, weights: dict[str, float]) -> dict:
    tags = list(meta.get("tags", []))
    if len(tags) > 1 and "no_result" in tags:
        tags = [t for t in tags if t != "no_result"]

    interval = CombatInterval(
        start=0.0, end=0.0, tags=frozenset(tags),
        k_delta=meta.get("killDelta", 0), a_delta=meta.get("assistDelta", 0),
        died=bool(meta.get("died")), day_night=meta.get("dayNight"), confidence=1.0,
        teammate_deaths=1 if "teammate_death" in tags else 0,
        enemy_ring_mean=meta.get("enemyRingMean"), game_day=meta.get("gameDay"),
    )
    result = score_interval(interval, weights)
    return {**meta, "tags": tags, "pvpScore": result.score, "pvpSignals": result.signals}


def rescore_folder(clips_dir: Path, weights: dict[str, float]) -> int:
    changed = 0
    for path in sorted(clips_dir.glob("*.json")):
        old = json.loads(path.read_text(encoding="utf-8"))
        new = rescore_meta(old, weights)
        if new != old:
            path.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
            changed += 1
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clips_dir", nargs="?", type=Path, default=Path.home() / "Videos/LumiaBriefingRoom/clips")
    args = parser.parse_args()
    changed = rescore_folder(args.clips_dir, FilterConfig().pvp_weights)
    print(f"{changed}개 클립의 점수를 다시 계산했다")


if __name__ == "__main__":
    main()
