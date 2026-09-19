"""일회성 조사 도구: 풀프레임에서 초상화 배지 색을 재
평상시(레벨) 배지가 매치마다 색이 달라도 '교전 주황'과 갈리는지 본다.

usage: badge_full.py <dir_of_fullres_pngs>
"""
import sys, glob, os
import numpy as np
from PIL import Image

X0, Y0, X1, Y1 = 680, 1395, 732, 1440
print(f"배지 ROI x{X0}..{X1} y{Y0}..{Y1}")
print(f"{'파일':>16} {'주황px':>7} {'파랑px':>7} {'노랑px':>7}   평균 RGB")
for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.png"))):
    a = np.array(Image.open(p).convert("RGB"))[Y0:Y1, X0:X1].astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    v = a.max(axis=2); s = v - a.min(axis=2)
    vivid = (v >= 90) & (s >= 60)
    orange = vivid & (r > b + 60) & (r >= g) & (g < r * 0.80)   # 주황: G가 R보다 뚜렷히 낮음
    yellow = vivid & (r > b + 60) & (g >= r * 0.80)             # 노랑: G가 R에 근접
    blue   = vivid & (b > r + 40)
    print(f"{os.path.basename(p):>16} {int(orange.sum()):7d} {int(blue.sum()):7d} {int(yellow.sum()):7d}   "
          f"({r.mean():5.1f},{g.mean():5.1f},{b.mean():5.1f})")
