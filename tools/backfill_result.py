"""이미 저장된 클립에 경기 결과(`matchResult`)를 채운다.

usage:
    python tools/backfill_result.py [clips_dir] [--recording-root DIR] [--ffmpeg PATH] [--force]

결과 화면은 클립 영상에 없고 원본 녹화에만 있다. 게임(sessionDir+matchStartUtc)별로 마지막 클립 뒤에서 앞으로 원본을 훑어
처음 나오는 결과 화면을 읽는다. 링버퍼가 이미 지운 경기는 건너뛴다. 영상 분석 동안 사용자가 라벨을 찍을 수 있어서 쓰기 직전에 다시 읽는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lumia_briefing_room.config import discover_ffmpeg  # noqa: E402
from lumia_briefing_room.detect.result import ResultScreen  # noqa: E402
from lumia_briefing_room.pipeline.metadata import match_result_dict  # noqa: E402
from lumia_briefing_room.pipeline.titles import retitle  # noqa: E402
from lumia_briefing_room.pipeline.result_scan import (  # noqa: E402
    find_result_after,
    result_image_name,
    save_result_image,
)
from lumia_briefing_room.steam_paths import discover_recording_root  # noqa: E402
from lumia_briefing_room.video.segments import segment_number_at  # noqa: E402
from lumia_briefing_room.video.session import RecordingSession, SessionParseError  # noqa: E402


@dataclass
class MatchGroup:
    ids: list[str] = field(default_factory=list)
    last_segment: int = 0


def apply_match_result(meta: dict, result: ResultScreen, image_path: str | None = None) -> dict:
    new = {**meta, "matchResult": match_result_dict(result, image_path)}
    if result.character and not new.get("myCharacter"):
        new["myCharacter"] = result.character
    mates = [t["character"] for t in result.teammates or [] if t.get("character")]
    if mates:
        new["teamCharacters"] = mates
    return retitle(new)


def group_by_match(metas: dict[str, dict]) -> dict[tuple[str, str], MatchGroup]:
    groups: dict[tuple[str, str], MatchGroup] = {}
    for clip_id, meta in metas.items():
        group = groups.setdefault((meta["sessionDir"], meta["matchStartUtc"]), MatchGroup())
        group.ids.append(clip_id)
        group.last_segment = max(group.last_segment, meta["segmentEnd"])
    return groups


def next_game_segment(session, session_name: str, match_start: str, groups: dict) -> int | None:
    """같은 세션에서 이 경기 다음에 시작한 경기의 시작 세그먼트. 없으면 None."""
    later = [
        datetime.fromisoformat(start.replace("Z", "+00:00"))
        for (name, start) in groups
        if name == session_name and start > match_start
    ]
    return segment_number_at(session, min(later)) if later else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clips_dir", nargs="?", type=Path, default=Path.home() / "Videos/LumiaBriefingRoom/clips")
    parser.add_argument("--recording-root", type=Path, default=None)
    parser.add_argument("--ffmpeg", type=Path, default=None)
    parser.add_argument("--force", action="store_true", help="결과가 이미 채워진 게임도 다시 읽는다")
    args = parser.parse_args()

    ffmpeg = args.ffmpeg or discover_ffmpeg()
    if ffmpeg is None:
        raise SystemExit("ffmpeg를 찾을 수 없다")
    root = args.recording_root or discover_recording_root()
    if root is None:
        raise SystemExit("녹화 폴더를 찾을 수 없다 - --recording-root 로 지정할 것")

    metas = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(args.clips_dir.glob("*.json"))}
    filled = missing_raw = not_found = skipped = 0
    groups = group_by_match(metas)
    for (session_name, match_start), group in sorted(groups.items()):
        if not args.force and all(metas[i].get("matchResult") for i in group.ids):
            skipped += 1
            continue
        session_dir = root / session_name
        if not session_dir.exists():
            missing_raw += 1
            continue
        try:
            session = RecordingSession.load(session_dir)
        except SessionParseError:
            missing_raw += 1
            continue

        result = find_result_after(
            session, group.last_segment, ffmpeg_path=ffmpeg,
            before_segment=next_game_segment(session, session_name, match_start, groups),
        )
        if result is None:
            not_found += 1
            print(f"{match_start}: 결과 화면을 못 찾았다(원본이 지워졌거나 결과 화면이 없다)")
            continue
        image_path = None
        if result.image is not None:
            start = datetime.fromisoformat(match_start.replace("Z", "+00:00"))
            image_path = str(args.clips_dir / ".thumbs" / result_image_name(start))
            save_result_image(result.image, Path(image_path))
        for clip_id in group.ids:
            path = args.clips_dir / f"{clip_id}.json"
            fresh = json.loads(path.read_text(encoding="utf-8"))
            path.write_text(
                json.dumps(apply_match_result(fresh, result, image_path), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        filled += 1
        print(f"{match_start}: {result.match_type} {result.placement}/{result.total} {result.outcome} ({len(group.ids)}개)")
    print(f"{filled}개 경기 채움, 이미 있음 {skipped}, 원본 없음 {missing_raw}, 못 찾음 {not_found}")


if __name__ == "__main__":
    main()
