"""일회성 조사 도구 v3: 안티에일리어싱 경계가 배경과 섞이는지 확인한다.
아주 높은 임계(코어만) vs 낮은 임계(경계 포함)로 마스크 동일성을 비교.

usage: glyph_stability3.py <dir_of_pngs>
"""
import sys, glob, os, hashlib, collections
import numpy as np
from PIL import Image

X0, X1, Y0, Y1 = 2455, 2486, 30, 49

def scan(v_min, s_max, erode):
    groups = collections.defaultdict(list)
    for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.png"))):
        rgb = np.array(Image.open(p).convert("RGB"))[Y0:Y1, X0:X1].astype(np.int16)
        v = rgb.max(axis=2); s = v - rgb.min(axis=2)
        m = ((v >= v_min) & (s <= s_max)).astype(np.uint8)
        if m.sum() < 15 or m.sum() > 200:   # 로비 아이콘 등 제외
            continue
        if erode:
            import cv2
            m = cv2.erode(m, np.ones((3, 3), np.uint8))
        groups[hashlib.md5(m.tobytes()).hexdigest()[:8]].append(os.path.basename(p))
    n = sum(len(v) for v in groups.values())
    big = sorted((len(v) for v in groups.values()), reverse=True)[:6]
    return n, len(groups), big

for v_min, s_max, erode in [(210, 40, False), (245, 15, False), (210, 40, True), (245, 15, True)]:
    n, g, big = scan(v_min, s_max, erode)
    print(f"V>={v_min:3d} S<={s_max:2d} erode={str(erode):5s} -> 프레임 {n}개, 고유마스크 {g}종, 상위군 크기 {big}")
