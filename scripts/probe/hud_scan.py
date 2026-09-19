"""일회성 조사 도구: 여러 프레임에서 우상단 킬 카운터 영역의
밝은 글리프 배치를 뽑아, 좌표 고정성과 자릿수 변화를 관찰한다.

usage: hud_scan.py <dir_of_pngs>
"""
import sys, glob, os
import numpy as np
from PIL import Image

X0, X1, Y0, Y1 = 2300, 2560, 25, 55
THRESH = 110

def runs_of(mask):
    cols = mask.any(axis=0)
    out, start = [], None
    for i, v in enumerate(cols):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i - 1)); start = None
    if start is not None:
        out.append((start, len(cols) - 1))
    return out

for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.png"))):
    img = np.array(Image.open(p).convert("L"))
    roi = img[Y0:Y1, X0:X1] > THRESH
    if not roi.any():
        print(f"{os.path.basename(p):16s} (HUD 없음 - 로비/로딩/관전 추정)")
        continue
    rs = runs_of(roi)
    ys = np.nonzero(roi.any(axis=1))[0]
    desc = " ".join(f"{X0+a}-{X0+b}" for a, b in rs)
    print(f"{os.path.basename(p):16s} glyphs={len(rs):2d} y={Y0+ys.min()}..{Y0+ys.max()} | {desc}")
