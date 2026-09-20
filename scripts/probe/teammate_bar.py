"""팀원 체력바 색(주황=사망/리스폰 대기, 초록=생존)으로 사망을 가를 수 있는지 잰다. (plan-pvp 2단계)

초상화 빨강은 캐릭터 머리색과 전투 링에 오염된다. 바 색은 그림과 무관하다.
"""
import subprocess, sys, tempfile
from pathlib import Path

import numpy as np
from PIL import Image

BARS = {"슬롯1": (2112, 1228, 2170, 1244), "슬롯2": (2112, 1365, 2170, 1381)}


def bar_stats(a):
    f = a.astype(np.float32)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    orange = ((r > 200) & (g > 100) & (g < 190) & (b < 90)).mean() * 100
    green = ((g > 170) & (r < 160) & (b < 120)).mean() * 100
    return float(orange), float(green)


def main(ffmpeg, names):
    root = Path.home() / "Videos/LumiaBriefingRoom/clips"
    for name in names:
        with tempfile.TemporaryDirectory() as td:
            subprocess.run([ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(root / f"{name}.mp4"),
                            "-vf", "fps=1/3", "-y", str(Path(td) / "f_%03d.png")], check=True)
            for slot, (x0, y0, x1, y1) in BARS.items():
                rows = []
                for p in sorted(Path(td).glob("*.png")):
                    a = np.asarray(Image.open(p).convert("RGB"))
                    rows.append(bar_stats(a[y0:y1, x0:x1]))
                o = [r[0] for r in rows]; g = [r[1] for r in rows]
                print(f"{name} {slot} 주황>2%:{sum(x > 2 for x in o):2d}/{len(o)} 초록>2%:{sum(x > 2 for x in g):2d}/{len(g)} "
                      f"| 주황&초록없음:{sum(1 for a_, b_ in rows if a_ > 2 and b_ < 0.5):2d}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
