"""일회성 조사 도구: 축소 프레임에서 화면 전체 채도를 재
'사망 시 회색 오버레이'가 실재하는지 찾는다.

usage: grey_scan.py <dir_of_small_pngs>
"""
import sys, glob, os
import numpy as np
from PIL import Image

print(f"{'세그먼트':>8}  {'평균채도':>8}  {'채도<12 비율':>12}  {'평균밝기':>8}")
for p in sorted(glob.glob(os.path.join(sys.argv[1], "s_*.png"))):
    a = np.array(Image.open(p).convert("RGB")).astype(np.int16)
    v = a.max(axis=2); s = v - a.min(axis=2)
    grey_ratio = float((s < 12).mean())
    bar = "#" * int(grey_ratio * 40)
    print(f"{os.path.basename(p)[2:7]:>8}  {s.mean():8.2f}  {grey_ratio:12.3f}  {v.mean():8.1f}  {bar}")
