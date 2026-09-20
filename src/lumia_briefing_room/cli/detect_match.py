"""매치 하나를 검출해 결과를 JSON 으로 출력하는 CLI. (plan.md §9-6)

usage:
    python -m lumia_briefing_room.cli.detect_match <session_dir> <match_start_iso> <match_end_iso>
        [--stream N] [--ffmpeg PATH] [--k-templates PATH] [--a-templates PATH] [--hwaccel NAME]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from lumia_briefing_room.config import FFMPEG_NOT_FOUND_MESSAGE, discover_ffmpeg
from lumia_briefing_room.detect.counter import load_templates
from lumia_briefing_room.detect.match import detect_match
from lumia_briefing_room.detect.types import MatchDetection
from lumia_briefing_room.video.segments import segment_time_range
from lumia_briefing_room.video.session import RecordingSession


def _parse_utc(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def result_to_json(result: MatchDetection) -> dict:
    return {
        "kFinal": result.k_final,
        "aFinal": result.a_final,
        "sourceIncomplete": result.source_incomplete,
        "gaps": result.gaps,
        "intervals": [
            {
                "start": iv.start,
                "end": iv.end,
                "tags": sorted(iv.tags),
                "kDelta": iv.k_delta,
                "aDelta": iv.a_delta,
                "died": iv.died,
                "dayNight": iv.day_night,
                "confidence": iv.confidence,
            }
            for iv in result.intervals
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("match_start", type=_parse_utc)
    parser.add_argument("match_end", type=_parse_utc)
    parser.add_argument("--stream", type=int, default=0)
    parser.add_argument("--ffmpeg", type=Path, default=None)
    parser.add_argument("--k-templates", type=Path, default=None)
    parser.add_argument("--a-templates", type=Path, default=None)
    parser.add_argument("--hwaccel", type=str, default=None)
    return parser


def run(args: argparse.Namespace) -> MatchDetection:
    session = RecordingSession.load(args.session_dir)
    seg_range = segment_time_range(session, args.match_start, args.match_end)

    ffmpeg_path = args.ffmpeg or discover_ffmpeg()
    if ffmpeg_path is None:
        raise SystemExit(FFMPEG_NOT_FOUND_MESSAGE)

    k_templates = load_templates(args.k_templates) if args.k_templates else None
    a_templates = load_templates(args.a_templates) if args.a_templates else None

    return detect_match(
        session,
        seg_range,
        stream=args.stream,
        ffmpeg_path=ffmpeg_path,
        k_templates=k_templates,
        a_templates=a_templates,
        hwaccel=args.hwaccel,
    )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = run(args)
    print(json.dumps(result_to_json(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
