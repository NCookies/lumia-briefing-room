"""이미 만들어진 클립의 일차·제목을 재처리 없이 채운다.

usage:
    python tools/backfill_day.py [clips_dir] [--ffmpeg PATH] [--force]

일차는 클립 영상 자체의 상단 HUD(`N일 차`)에서 읽는다. 키프레임(3초마다 1장)만 디코딩한다. 원본 녹화가 없어도 된다.
사용자 라벨과 사용자가 직접 바꾼 제목은 건드리지 않는다(자동 제목일 때만 갱신).
영상 분석에 몇 초 걸리는 동안 사용자가 라벨을 찍을 수 있어서, 쓰기 직전에 메타데이터를 다시 읽는다.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lumia_briefing_room.config import discover_ffmpeg  # noqa: E402
from lumia_briefing_room.detect.day import read_game_day  # noqa: E402
from lumia_briefing_room.detect.region import load_region_templates  # noqa: E402
from lumia_briefing_room.pipeline.metadata import phase_index, revive_cost  # noqa: E402
from lumia_briefing_room.pipeline.orchestrator import default_title  # noqa: E402
from lumia_briefing_room.profiles.models import ResolutionProfile  # noqa: E402


def most_common_day(days: list[int | None]) -> int | None:
    known = [d for d in days if d is not None]
    return Counter(known).most_common(1)[0][0] if known else None


def apply_game_day(meta: dict, day: int | None) -> dict:
    if day is None:
        return meta
    day_night = meta.get("dayNight")
    phase = phase_index(day, day_night) if day_night else None
    result = {
        **meta,
        "gameDay": day,
        "phaseIndex": phase,
        "reviveCost": revive_cost(phase) if phase is not None else None,
    }
    region = meta.get("region")
    auto_titles = {default_title(day_night, region), default_title(day_night, region, meta.get("gameDay"))}
    if meta.get("title") in auto_titles:
        result["title"] = default_title(day_night, region, day)
    return result


def padded_crop(roi) -> tuple[str, slice, slice]:
    """yuv420p 에서 ffmpeg crop 은 좌표·폭을 짝수로 반올림한다. 짝수로 넉넉히 자른 뒤 정확한 ROI 만 슬라이스한다."""
    x0, y0 = roi.x0 & ~1, roi.y0 & ~1
    w = (roi.x1 - x0 + 1) & ~1
    h = (roi.y1 - y0 + 1) & ~1
    return f"crop={w}:{h}:{x0}:{y0}", slice(roi.y0 - y0, roi.y1 - y0), slice(roi.x0 - x0, roi.x1 - x0)


def read_clip_day(clip_mp4: Path, profile: ResolutionProfile, templates, ffmpeg: Path) -> int | None:
    crop, rows, cols = padded_crop(profile.rois["day_digit"])
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(
            [str(ffmpeg), "-nostdin", "-loglevel", "error", "-skip_frame", "nokey", "-i", str(clip_mp4),
             "-vf", crop, "-pix_fmt", "rgb24", "-fps_mode", "passthrough", "-y", str(Path(td) / "c_%03d.png")],
            check=True,
        )
        days = [
            read_game_day(np.asarray(Image.open(p).convert("RGB"))[rows, cols], templates)
            for p in sorted(Path(td).glob("c_*.png"))
        ]
    return most_common_day(days)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clips_dir", nargs="?", type=Path, default=Path.home() / "Videos/LumiaBriefingRoom/clips")
    parser.add_argument("--ffmpeg", type=Path, default=None)
    parser.add_argument("--force", action="store_true", help="일차가 이미 채워진 클립도 다시 읽는다")
    args = parser.parse_args()

    ffmpeg = args.ffmpeg or discover_ffmpeg()
    if ffmpeg is None:
        raise SystemExit("ffmpeg를 찾을 수 없다")

    updated = unchanged = unread = 0
    for meta_path in sorted(args.clips_dir.glob("*.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("gameDay") is not None and not args.force:
            continue
        profile = ResolutionProfile.for_resolution(meta["sourceWidth"], meta["sourceHeight"])
        if profile.day_templates is None:
            unread += 1
            continue
        day = read_clip_day(
            meta_path.with_suffix(".mp4"), profile, load_region_templates(profile.day_templates), ffmpeg
        )
        fresh = json.loads(meta_path.read_text(encoding="utf-8"))
        new = apply_game_day(fresh, day)
        if day is None:
            unread += 1
            continue
        if new == fresh:
            unchanged += 1
            continue
        meta_path.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
        updated += 1
        print(f"{meta_path.stem}: {new['title']}")
    print(f"{updated}개 갱신, {unchanged}개는 이미 맞음, {unread}개는 일차를 못 읽었다")


if __name__ == "__main__":
    main()
