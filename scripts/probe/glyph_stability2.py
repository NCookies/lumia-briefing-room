"""일회성 조사 도구 v2: 킬 카운터 숫자를 '거의 흰색(고휘도+저채도)' 조건으로
뽑아, 같은 값이 픽셀 단위로 동일하게 렌더되는지 본다.
HUD 텍스트에 배경판이 없어 단순 휘도 임계로는 배경이 섞인다.

usage: glyph_stability2.py <dir_of_pngs>
"""
import sys, glob, os, hashlib
import numpy as np
from PIL import Image

X0, X1, Y0, Y1 = 2455, 2486, 30, 49     # K 값 필드(1~2자리 모두 포함)
V_MIN, S_MAX = 210, 40                   # 밝기 하한 / 채도 상한

groups = {}
for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.png"))):
    rgb = np.array(Image.open(p).convert("RGB"))[Y0:Y1, X0:X1].astype(np.int16)
    v = rgb.max(axis=2)
    s = v - rgb.min(axis=2)
    mask = ((v >= V_MIN) & (s <= S_MAX)).astype(np.uint8)
    if mask.sum() < 15:
        continue
    key = hashlib.md5(mask.tobytes()).hexdigest()[:10]
    groups.setdefault(key, []).append((os.path.basename(p), int(mask.sum())))

print(f"ROI x[{X0},{X1}) y[{Y0},{Y1})  V>={V_MIN} S<={S_MAX}")
print(f"프레임 {sum(len(v) for v in groups.values())}개 -> 서로 다른 비트마스크 {len(groups)}종\n")
for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    print(f"  {k}  {len(v):2d}장  px={v[0][1]:3d}  {', '.join(n for n, _ in v[:6])}")
