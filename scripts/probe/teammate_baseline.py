"""팀원 초상화 원판의 엄격한 빨강 비율 — 생존 기준선을 전체 클립에서 잰다. (plan-pvp 2단계)

빨간 머리 캐릭터나 분홍 링이 오탐하지 않는지 본다. 분홍 링은 파랑 성분이 남아 b < 0.45r 에서 걸러진다.
"""
import subprocess, sys, tempfile
from pathlib import Path

import numpy as np
from PIL import Image

DISCS = {"슬롯1": (2100, 1165, 2180, 1225), "슬롯2": (2100, 1302, 2180, 1362)}


def strict_red(a):
    f = a.astype(np.float32)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    return float(((r > 110) & (g < 0.45 * r) & (b < 0.45 * r)).mean() * 100)


def main(ffmpeg):
    clips = sorted((Path.home() / "Videos/LumiaBriefingRoom/clips").glob("*.mp4"))
    for c in clips:
        with tempfile.TemporaryDirectory() as td:
            subprocess.run([ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(c),
                            "-vf", "fps=1/3", "-y", str(Path(td) / "f_%03d.png")], check=True)
            rows = {k: [] for k in DISCS}
            for p in sorted(Path(td).glob("*.png")):
                a = np.asarray(Image.open(p).convert("RGB"))
                for k, (x0, y0, x1, y1) in DISCS.items():
                    rows[k].append(strict_red(a[y0:y1, x0:x1]))
        print(c.stem, " | ".join(f"{k} 최대{max(v):5.1f} 3%초과 {sum(x > 3 for x in v)}" for k, v in rows.items() if v), flush=True)
    print("완료", len(clips), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
