"""라벨링용 프레임을 수집한다. (plan.md §2, §9-7)

세그먼트별 키프레임 풀해상도 프레임을 PNG로 저장한다.
scripts/probe/sample_segments.sh 의 역할을 이어받되 파이썬 파이프라인을 그대로 쓴다.

usage:
    python tools/collect_frames.py <session_dir> <first_segment> <last_segment> <step> <out_dir>
        [--ffmpeg PATH] [--stream N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lumia_briefing_room.config import discover_ffmpeg  # noqa: E402
from lumia_briefing_room.video.frames import extract_keyframe_frames  # noqa: E402
from lumia_briefing_room.video.session import RecordingSession  # noqa: E402


def collect(
    session: RecordingSession,
    first: int,
    last: int,
    step: int,
    out_dir: Path,
    *,
    ffmpeg_path: Path,
    stream: int = 0,
) -> list[int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    numbers = list(range(first, last + 1, step))
    saved: list[int] = []
    for seg_num, frame in extract_keyframe_frames(
        session, stream=stream, segment_numbers=numbers, ffmpeg_path=ffmpeg_path
    ):
        _save_frame(frame, out_dir / f"seg_{seg_num:05d}.png")
        saved.append(seg_num)
    return saved


def _save_frame(frame: np.ndarray, path: Path) -> None:
    Image.fromarray(frame).save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("first", type=int)
    parser.add_argument("last", type=int)
    parser.add_argument("step", type=int)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--ffmpeg", type=Path, default=None)
    parser.add_argument("--stream", type=int, default=0)
    args = parser.parse_args()

    ffmpeg_path = args.ffmpeg or discover_ffmpeg()
    if ffmpeg_path is None:
        raise SystemExit("ffmpeg 를 찾을 수 없다")

    session = RecordingSession.load(args.session_dir)
    saved = collect(
        session, args.first, args.last, args.step, args.out_dir,
        ffmpeg_path=ffmpeg_path, stream=args.stream,
    )
    print(f"{len(saved)}개 저장: {args.out_dir}")


if __name__ == "__main__":
    main()
