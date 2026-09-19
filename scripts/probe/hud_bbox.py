"""일회성 조사 도구: 프레임에서 HUD 텍스트(밝은 픽셀) 덩어리의 정확한 bbox를 잰다.

usage: hud_bbox.py <png> [x0 y0 x1 y1] [thresh]
"""
import sys
import numpy as np
from PIL import Image

path = sys.argv[1]
img = np.array(Image.open(path).convert("L"))
H, W = img.shape
x0, y0, x1, y1 = (int(v) for v in sys.argv[2:6]) if len(sys.argv) >= 6 else (0, 0, W, H)
thresh = int(sys.argv[6]) if len(sys.argv) >= 7 else 200

print(f"image {W}x{H}  region x[{x0},{x1}) y[{y0},{y1})  thresh>{thresh}")
roi = img[y0:y1, x0:x1]
mask = roi > thresh
if not mask.any():
    print("no bright pixels")
    sys.exit(0)

ys, xs = np.nonzero(mask)
print(f"tight bbox (absolute): x={x0+xs.min()}..{x0+xs.max()}  y={y0+ys.min()}..{y0+ys.max()}"
      f"  (w={xs.max()-xs.min()+1} h={ys.max()-ys.min()+1})")

# 글리프 단위로 쪼개기: 빈 열로 분리되는 구간
cols = mask.any(axis=0)
runs, start = [], None
for i, v in enumerate(cols):
    if v and start is None:
        start = i
    elif not v and start is not None:
        runs.append((start, i - 1))
        start = None
if start is not None:
    runs.append((start, len(cols) - 1))

print(f"\ncolumn runs ({len(runs)}개):")
for a, b in runs:
    sub = mask[:, a:b + 1]
    sy = np.nonzero(sub.any(axis=1))[0]
    print(f"  x={x0+a}..{x0+b} (w={b-a+1})  y={y0+sy.min()}..{y0+sy.max()} (h={sy.max()-sy.min()+1})")
