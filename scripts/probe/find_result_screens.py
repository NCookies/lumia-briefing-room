"""녹화 세션에서 인게임이 끝나고 비인게임(결과·로비)이 시작되는 지점의 프레임을 저장한다. (결과 화면 조사용)

usage: find_result_screens.py <session_dir> <out_dir> [--step 2] [--after 5]
인게임 판정은 상단 HUD `N일 차` 를 읽을 수 있느냐로 한다. 인게임→비인게임 전환마다 그 뒤 `after` 프레임을 저장한다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lumia_briefing_room.config import discover_ffmpeg  # noqa: E402
from lumia_briefing_room.detect.day import read_game_day  # noqa: E402
from lumia_briefing_room.detect.region import load_region_templates  # noqa: E402
from lumia_briefing_room.profiles.models import ResolutionProfile  # noqa: E402
from lumia_briefing_room.video.frames import crop_roi, extract_keyframe_frames  # noqa: E402
from lumia_briefing_room.video.segments import existing_segment_numbers  # noqa: E402
from lumia_briefing_room.video.session import RecordingSession  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("session_dir", type=Path)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--step", type=int, default=2)
    p.add_argument("--after", type=int, default=5)
    args = p.parse_args()

    ffmpeg = discover_ffmpeg()
    session = RecordingSession.load(args.session_dir)
    profile = ResolutionProfile.for_resolution(session.width, session.height)
    templates = load_region_templates(profile.day_templates)
    nums = existing_segment_numbers(session, 0, 1, 100000)[:: args.step]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    prev_ingame = False
    since_exit = 10**9
    for n, frame in extract_keyframe_frames(session, stream=0, segment_numbers=nums, ffmpeg_path=ffmpeg):
        ingame = read_game_day(crop_roi(frame, profile.rois["day_digit"]), templates) is not None
        if prev_ingame and not ingame:
            since_exit = 0
            print(f"in-game 끝: seg {n}", flush=True)
        if not ingame and since_exit < args.after:
            Image.fromarray(frame).save(args.out_dir / f"seg_{n:05d}_after{since_exit}.png")
            since_exit += 1
        elif not ingame:
            since_exit += 1
        prev_ingame = ingame


if __name__ == "__main__":
    main()
