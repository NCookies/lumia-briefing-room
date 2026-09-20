"""회색 화면(팀 전멸/BREAK 부활 대기)을 전체 클립에서 훑는다. (SPEC 4단계)

제보: 1일차에 전멸당하면(BREAK) 회색 화면 + 중앙에 흰 숫자로 부활 카운트다운이
뜬다. 여러 번 일어날 수 있다. 자료가 없어 실제 녹화본에서 찾는다.

판정: 화면 전체 채도가 낮고(회색) 완전 암전은 아닌 프레임.
"""
import subprocess, sys, tempfile
from pathlib import Path

import numpy as np
from PIL import Image


def frame_stats(path):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    mx, mn = a.max(axis=2), a.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0).mean() * 100
    return float(a.mean()), float(sat)


def scan(ffmpeg, clip, step=2):
    with tempfile.TemporaryDirectory() as td:
        subprocess.run([ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(clip),
                        "-vf", f"fps=1/{step},scale=480:-1", "-y", str(Path(td) / "f_%03d.png")],
                       check=True)
        return [(int(p.stem[-3:]), *frame_stats(p)) for p in sorted(Path(td).glob("*.png"))]


if __name__ == "__main__":
    ff = sys.argv[1]
    clips = sorted((Path.home() / "Videos/LumiaBriefingRoom/clips").glob("*.mp4"))
    for c in clips:
        hits = [(i, b, s) for i, b, s in scan(ff, c) if s < 16 and b > 18]
        if hits:
            print(f"{c.stem}: " + ", ".join(f"#{i}(밝기{b:.0f},채도{s:.1f})" for i, b, s in hits))
    print("스캔 완료", len(clips), "클립")
