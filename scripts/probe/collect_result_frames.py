"""경기 종료 직전 키프레임을 수집한다. (결과 화면 판독 조사용)

usage: collect_result_frames.py <recording_root> <out_dir> [--tail 12] [--ffmpeg PATH]

Player.log / Player-prev.log 의 매치 경계를 읽어 남아 있는 세션에서 종료 시각 앞 `tail` 개 세그먼트(3초씩)의 키프레임을 저장한다.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lumia_briefing_room.config import discover_ffmpeg  # noqa: E402
from lumia_briefing_room.pipeline.playerlog import extract_matches  # noqa: E402
from lumia_briefing_room.pipeline.watcher import find_session_for_time  # noqa: E402
from lumia_briefing_room.video.frames import extract_keyframe_frames  # noqa: E402
from lumia_briefing_room.video.segments import existing_segment_numbers, segment_number_at  # noqa: E402
from lumia_briefing_room.video.session import RecordingSession  # noqa: E402

LOG_DIR = Path.home() / "AppData/LocalLow/NimbleNeuron/Eternal Return"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("recording_root", type=Path)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--tail", type=int, default=12)
    p.add_argument("--ffmpeg", type=Path, default=None)
    args = p.parse_args()
    ffmpeg = args.ffmpeg or discover_ffmpeg()

    local_tz = datetime.now().astimezone().tzinfo
    lines: list[str] = []
    for name in ("Player-prev.log", "Player.log"):
        f = LOG_DIR / name
        if f.exists():
            lines += f.read_text(encoding="utf-8", errors="replace").splitlines()
    matches = [m for m in extract_matches(lines, local_tz=local_tz) if m.end_utc]

    root = args.recording_root / "video"
    for m in matches:
        sdir = find_session_for_time(root, m.end_utc)
        if sdir is None:
            continue
        session = RecordingSession.load(sdir)
        end_seg = segment_number_at(session, m.end_utc)
        nums = [n for n in existing_segment_numbers(session, 0, end_seg - args.tail, end_seg)]
        if not nums:
            continue
        out = args.out_dir / f"{m.start_utc:%Y%m%d_%H%M%S}"
        out.mkdir(parents=True, exist_ok=True)
        for n, frame in extract_keyframe_frames(
            session, stream=0, segment_numbers=nums, ffmpeg_path=ffmpeg
        ):
            Image.fromarray(frame).save(out / f"seg_{n:05d}_end{end_seg - n:+d}.png")
        print(out.name, len(nums), flush=True)


if __name__ == "__main__":
    main()
