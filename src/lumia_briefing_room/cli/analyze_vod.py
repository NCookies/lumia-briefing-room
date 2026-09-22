"""다시보기 영상 하나를 분석해 게임별 교전 클립을 만든다. (docs/plan-vod.md)

usage:
    python -m lumia_briefing_room.cli.analyze_vod <video> [--config PATH] [--ffmpeg PATH]
        [--clips-dir PATH] [--streamer NAME] [--hwaccel NAME] [--force] [--rebuild]

클립은 스팀 클립과 다른 폴더(paths.vodClips)에 만들어진다. 중간에 Ctrl+C 로 멈추면 다음에 이어서 한다.
"""

from __future__ import annotations

import argparse
import threading
from pathlib import Path

from lumia_briefing_room.config import FFMPEG_NOT_FOUND_MESSAGE, discover_ffmpeg, load_config
from lumia_briefing_room.pipeline.vod_analyze import VodCancelled, VodProgress, analyze_vod


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--ffmpeg", type=Path, default=None)
    parser.add_argument("--clips-dir", type=Path, default=None)
    parser.add_argument("--streamer", type=str, default=None)
    parser.add_argument("--hwaccel", type=str, default=None)
    parser.add_argument("--force", action="store_true", help="캐시까지 지우고 처음부터 다시 분석")
    parser.add_argument("--rebuild", action="store_true", help="캐시로 클립만 다시 만든다(재디코딩 없음)")
    return parser


def _print_progress(progress: VodProgress) -> None:
    print(
        f"[{progress.phase:6}] {progress.fraction * 100:5.1f}%  게임 {progress.games}  클립 {progress.clips}  {progress.message}",
        flush=True,
    )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    cfg = load_config(args.config)
    ffmpeg_path = args.ffmpeg or discover_ffmpeg()
    if ffmpeg_path is None:
        raise SystemExit(FFMPEG_NOT_FOUND_MESSAGE)
    if not args.video.exists():
        raise SystemExit(f"영상 파일이 없다: {args.video}")

    cancel = threading.Event()
    try:
        index = analyze_vod(
            args.video, cfg, ffmpeg_path=ffmpeg_path, clips_dir=args.clips_dir,
            streamer=args.streamer, hwaccel=args.hwaccel, force=args.force,
            rebuild=args.rebuild, on_progress=_print_progress, cancel=cancel,
        )
    except (KeyboardInterrupt, VodCancelled):
        cancel.set()
        raise SystemExit("중단했다. 같은 명령을 다시 실행하면 이어서 한다.")

    print(f"게임 {len(index['games'])}판, 클립 {len(index['clips'])}개 ({index['status']})")
    if index.get("labelsMigrated"):
        conflicts = index.get("labelConflicts", 0)
        print(f"옛 클립의 라벨 {index['labelsMigrated']}개를 새 클립으로 옮겼다" + (f" (교전·사냥이 섞여 확인이 필요한 것 {conflicts}개)" if conflicts else ""))
    for game in index["games"]:
        result = game.get("result") or {}
        placement = f"{result.get('placement')}/{result.get('total')}위" if result.get("placement") else "결과 미확인"
        print(
            f"  게임 {game['index']}: {game['startSec']:.0f}~{game['endSec']:.0f}초  {placement}  "
            f"K {game['kFinal']} A {game['aFinal']}  클립 {len(game['clipIds'])}개"
        )


if __name__ == "__main__":
    main()
