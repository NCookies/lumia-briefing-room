"""일회성 조사 도구: 여러 프레임에서 킬 카운터 K 필드 ROI를 떼어내
같은 숫자가 픽셀 단위로 동일하게 렌더되는지(=템플릿 매칭 가능한지) 본다.

usage: glyph_stability.py <dir_of_pngs>
"""
import sys, glob, os, hashlib
import numpy as np
from PIL import Image

# K 필드: 라벨 K(2437..2449) + 값(1자리 2464..2474 / 2두자리 2458..2481)
ROI = dict(x0=2430, x1=2490, y0=29, y1=50)
THRESH = 110

groups = {}
for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.png"))):
    a = np.array(Image.open(p).convert("L"))[ROI["y0"]:ROI["y1"], ROI["x0"]:ROI["x1"]]
    mask = (a > THRESH).astype(np.uint8)
    if mask.sum() < 20:
        continue
    key = hashlib.md5(mask.tobytes()).hexdigest()[:10]
    groups.setdefault(key, []).append(os.path.basename(p))

print(f"ROI x[{ROI['x0']},{ROI['x1']}) y[{ROI['y0']},{ROI['y1']}) thresh>{THRESH}")
print(f"HUD 있는 프레임 {sum(len(v) for v in groups.values())}개 -> 서로 다른 비트마스크 {len(groups)}종\n")
for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    print(f"  {k}  {len(v):2d}장  {v[0]} ...")
