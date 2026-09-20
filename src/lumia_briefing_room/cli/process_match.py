"""매치 하나를 끝까지 처리한다: 검출 -> 필터 -> 컷 -> 썸네일 -> 메타데이터. (plan-pipeline.md §2.6)

usage:
    python -m lumia_briefing_room.cli.process_match <session_dir> <match_start_iso> <match_end_iso>
        [--config PATH] [--ffmpeg PATH] [--game-mode battle_royale|cobalt]
        [--k-templates PATH] [--a-templates PATH] [--clips-dir PATH] [--hwaccel NAME]
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from lumia_briefing_room.config import FFMPEG_NOT_FOUND_MESSAGE, discover_ffmpeg, load_config
from lumia_briefing_room.detect.counter import load_templates
from lumia_briefing_room.pipeline.orchestrator import process_match
from lumia_briefing_room.video.session import RecordingSession


def _parse_utc(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("match_start", type=_parse_utc)
    parser.add_argument("match_end", type=_parse_utc)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--ffmpeg", type=Path, default=None)
    parser.add_argument("--game-mode", default="battle_royale")
    parser.add_argument("--k-templates", type=Path, default=None)
    parser.add_argument("--a-templates", type=Path, default=None)
    parser.add_argument("--clips-dir", type=Path, default=None)
    parser.add_argument("--hwaccel", type=str, default=None)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    cfg = load_config(args.config)
    ffmpeg_path = args.ffmpeg or discover_ffmpeg()
    if ffmpeg_path is None:
        raise SystemExit(FFMPEG_NOT_FOUND_MESSAGE)

    session = RecordingSession.load(args.session_dir)
    k_templates = load_templates(args.k_templates) if args.k_templates else None
    a_templates = load_templates(args.a_templates) if args.a_templates else None

    written = process_match(
        session, args.match_start, args.match_end, cfg,
        ffmpeg_path=ffmpeg_path, game_mode=args.game_mode,
        k_templates=k_templates, a_templates=a_templates,
        clips_dir=args.clips_dir, hwaccel=args.hwaccel,
    )

    if not written:
        print("클립 없음 (필터 통과한 교전이 없거나 교전이 없었다)")
        return
    for path in written:
        print(path)


if __name__ == "__main__":
    main()
