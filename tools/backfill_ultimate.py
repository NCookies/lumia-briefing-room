"""이미 만들어진 클립에 궁극기(R) 사용 신호를 재처리 없이 채운다.

usage:
    python tools/backfill_ultimate.py [clips_dir] [--ffmpeg PATH] [--force]

2026-09-22 이전에 만든 클립은 ultimateDelta 필드 자체가 없다(SPEC §2.12 #9). 원본 녹화가
없어도 클립 영상 자체의 R 칸(HUD)에서 다시 읽을 수 있다 - backfill_day.py 와 같은 방식.
키프레임(3초마다 1장, `-c copy` 로 자른 클립이라 원본 간격 그대로)만 디코딩한다.

클립 전체에서 최솟값 대비 최댓값 차이(delta)를 재는 것까지가 실제 라벨 검증(AUC 0.914,
scripts/probe/eval_ultimate_signal.py) 과 정확히 같은 방식이다 - 운영 중인 탐지 파이프라인은
구간 앞뒤 12초만 보지만(detect/match.py), 여기서는 클립 전체를 보므로 오히려 원본 검증에 더
가깝다.

사용자 라벨과 제목은 건드리지 않는다. pvpScore/pvpSignals 는 새 증거를 더해 다시 계산한다
(rescore_clips.rescore_meta 재사용 - 더 강한 기존 증거가 있으면 그대로 이긴다).
영상 분석에 몇 초 걸리는 동안 사용자가 라벨을 찍을 수 있어서, 쓰기 직전에 메타데이터를 다시 읽는다.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lumia_briefing_room.config import FilterConfig, discover_ffmpeg  # noqa: E402
from lumia_briefing_room.detect.ultimate import blue_tint_ratio  # noqa: E402
from lumia_briefing_room.profiles.models import ResolutionProfile  # noqa: E402

from backfill_day import padded_crop  # noqa: E402
from rescore_clips import rescore_meta  # noqa: E402


def apply_ultimate_delta(meta: dict, delta: float | None, weights: dict[str, float]) -> dict:
    if delta is None:
        return meta
    return rescore_meta({**meta, "ultimateDelta": delta}, weights)


def read_clip_ultimate_delta(clip_mp4: Path, profile: ResolutionProfile, ffmpeg: Path) -> float | None:
    crop, rows, cols = padded_crop(profile.rois["ultimate_r"])
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(
            [str(ffmpeg), "-nostdin", "-loglevel", "error", "-skip_frame", "nokey", "-i", str(clip_mp4),
             "-vf", crop, "-pix_fmt", "rgb24", "-fps_mode", "passthrough", "-y", str(Path(td) / "c_%03d.png")],
            check=True,
        )
        ratios = [
            blue_tint_ratio(np.asarray(Image.open(p).convert("RGB"))[rows, cols])
            for p in sorted(Path(td).glob("c_*.png"))
        ]
    if len(ratios) < 2:
        return None
    return max(ratios) - min(ratios)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clips_dir", nargs="?", type=Path, default=Path.home() / "Videos/LumiaBriefingRoom/clips")
    parser.add_argument("--ffmpeg", type=Path, default=None)
    parser.add_argument("--force", action="store_true", help="ultimateDelta 가 이미 채워진 클립도 다시 읽는다")
    args = parser.parse_args()

    ffmpeg = args.ffmpeg or discover_ffmpeg()
    if ffmpeg is None:
        raise SystemExit("ffmpeg를 찾을 수 없다")

    weights = FilterConfig().pvp_weights
    updated = unchanged = unread = 0
    for meta_path in sorted(args.clips_dir.glob("*.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("ultimateDelta") is not None and not args.force:
            continue
        profile = ResolutionProfile.for_resolution(meta["sourceWidth"], meta["sourceHeight"])
        if "ultimate_r" not in profile.rois:
            unread += 1
            continue
        delta = read_clip_ultimate_delta(meta_path.with_suffix(".mp4"), profile, ffmpeg)
        if delta is None:
            unread += 1
            continue
        fresh = json.loads(meta_path.read_text(encoding="utf-8"))
        new = apply_ultimate_delta(fresh, delta, weights)
        if new == fresh:
            unchanged += 1
            continue
        meta_path.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
        updated += 1
        print(f"{meta_path.stem}: delta={delta:.3f} -> score={new['pvpScore']} signals={new['pvpSignals']}")
    print(f"{updated}개 갱신, {unchanged}개는 이미 맞음, {unread}개는 못 읽었다")


if __name__ == "__main__":
    main()
