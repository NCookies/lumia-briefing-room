"""일회성 조사 도구: 초상화 좌하단 배지의 색을 재
'평상시 파랑(레벨)' vs '교전 중 주황(교차 칼)' 을 구분할 수 있는지 본다.

usage: badge_color.py <dir_of_portrait_crops> <crop_origin_x> <crop_origin_y>
       (크롭은 crop=230:200:640:1240 로 뜬 것 기준)
"""
import sys, glob, os
import numpy as np
from PIL import Image

d = sys.argv[1]
OX, OY = int(sys.argv[2]), int(sys.argv[3])
# 배지 ROI (원본 좌표) -> 크롭 내 좌표로 변환
BADGE = (680, 1395, 732, 1440)
x0, y0 = BADGE[0] - OX, BADGE[1] - OY
x1, y1 = BADGE[2] - OX, BADGE[3] - OY

print(f"배지 ROI(원본) x{BADGE[0]}..{BADGE[2]} y{BADGE[1]}..{BADGE[3]}")
print(f"{'seg':>6} {'주황px':>7} {'파랑px':>7} {'판정':>8}   평균 RGB")
for p in sorted(glob.glob(os.path.join(d, "g_*.png"))):
    a = np.array(Image.open(p).convert("RGB"))[y0:y1, x0:x1].astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    v = a.max(axis=2); s = v - a.min(axis=2)
    vivid = (v >= 90) & (s >= 60)          # 선명한 색만
    orange = vivid & (r > b + 60) & (r >= g)
    blue   = vivid & (b > r + 40)
    no, nb = int(orange.sum()), int(blue.sum())
    verdict = "교전" if no > nb * 1.5 and no > 60 else ("평상" if nb > 60 else "?")
    print(f"{os.path.basename(p)[2:7]:>6} {no:7d} {nb:7d} {verdict:>8}   "
          f"({a[...,0].mean():5.1f},{a[...,1].mean():5.1f},{a[...,2].mean():5.1f})")
