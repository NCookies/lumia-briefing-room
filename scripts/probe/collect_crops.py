"""전체 클립에서 고정 ROI crop 을 수집한다. (plan-pvp 3단계 일차 판독용)

usage: collect_crops.py <ffmpeg> <out_dir> <x> <y> <w> <h> [fps_denominator]
"""
import subprocess, sys
from pathlib import Path


def main(ffmpeg, out_dir, x, y, w, h, every=6):
    out = Path(out_dir)
    for clip in sorted((Path.home() / "Videos/LumiaBriefingRoom/clips").glob("*.mp4")):
        d = out / clip.stem
        d.mkdir(parents=True, exist_ok=True)
        subprocess.run([ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(clip),
                        "-vf", f"fps=1/{every},crop={w}:{h}:{x}:{y}", "-y", str(d / "c_%03d.png")], check=True)
        print(clip.stem, len(list(d.glob("*.png"))), flush=True)


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], *map(int, a[3:7]), int(a[7]) if len(a) > 7 else 6)
