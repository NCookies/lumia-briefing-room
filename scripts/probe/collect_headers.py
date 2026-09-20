"""미니맵 헤더 지역명 crop 을 전체 클립에서 수집한다. (plan-pvp 3단계)"""
import subprocess, sys
from pathlib import Path

CROP = "crop=200:34:2210:1080"


def main(ffmpeg, out_dir):
    out = Path(out_dir)
    for clip in sorted((Path.home() / "Videos/LumiaBriefingRoom/clips").glob("*.mp4")):
        d = out / clip.stem
        d.mkdir(parents=True, exist_ok=True)
        subprocess.run([ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(clip),
                        "-vf", f"fps=1/3,{CROP}", "-y", str(d / "h_%03d.png")], check=True)
        print(clip.stem, len(list(d.glob("*.png"))), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
