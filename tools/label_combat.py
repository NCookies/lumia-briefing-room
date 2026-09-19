"""교전 구간 라벨 초안을 만든다. (plan.md §2, §9-7)

검출기 결과를 그대로 labels.jsonl 형식의 초안으로 저장한다. 자동 라벨링이
아니라 초안 생성이다 - 사람이 저장된 프레임(collect_frames.py)을 보며
combats/deaths 를 직접 검토·수정한 뒤 eval_detect.py 의 정답지로 쓴다.

usage:
    python tools/label_combat.py <session_dir> <match_start_iso> <match_end_iso> <output.jsonl>
        [--ffmpeg PATH] [--stream N]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lumia_briefing_room.config import discover_ffmpeg  # noqa: E402
from lumia_briefing_room.detect.match import detect_match  # noqa: E402
from lumia_briefing_room.video.segments import segment_time_range  # noqa: E402
from lumia_briefing_room.video.session import RecordingSession  # noqa: E402


def _parse_utc(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def draft_label(
    session: RecordingSession,
    match_start: datetime,
    match_end: datetime,
    *,
    ffmpeg_path: Path,
    stream: int = 0,
) -> dict:
    seg_range = segment_time_range(session, match_start, match_end)
    result = detect_match(session, seg_range, stream=stream, ffmpeg_path=ffmpeg_path)
    return {
        "session_dir": str(session.directory),
        "match_start": match_start.isoformat(),
        "match_end": match_end.isoformat(),
        "combats": [[iv.start, iv.end] for iv in result.intervals],
        "deaths": [],
        "k_final": result.k_final,
        "a_final": result.a_final,
    }


def append_label(path: Path, label: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(label, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("match_start", type=_parse_utc)
    parser.add_argument("match_end", type=_parse_utc)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ffmpeg", type=Path, default=None)
    parser.add_argument("--stream", type=int, default=0)
    args = parser.parse_args()

    ffmpeg_path = args.ffmpeg or discover_ffmpeg()
    if ffmpeg_path is None:
        raise SystemExit("ffmpeg 를 찾을 수 없다")

    session = RecordingSession.load(args.session_dir)
    label = draft_label(
        session, args.match_start, args.match_end,
        ffmpeg_path=ffmpeg_path, stream=args.stream,
    )
    append_label(args.output, label)
    print(f"초안 {len(label['combats'])}개 교전 구간 -> {args.output}")
    print("deaths 는 비어 있다. 사람이 직접 채워야 한다.")


if __name__ == "__main__":
    main()
