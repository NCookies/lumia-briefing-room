"""일회성 조사 도구: 사망 시 '월드 레이어 회색화'를 정량화한다.
HUD는 색을 유지하므로 화면 전체가 아니라 중앙(월드) 영역만 재야 신호가 산다.

usage: death_metric.py <dir_of_small_pngs> <prefix>
"""
import sys, glob, os
import numpy as np
from PIL import Image

d, prefix = sys.argv[1], sys.argv[2]
print(f"{'t(s)':>6} {'전체채도':>8} {'중앙채도':>8} {'중앙밝기':>8}  중앙채도 그래프")
for p in sorted(glob.glob(os.path.join(d, prefix + "*.png"))):
    a = np.array(Image.open(p).convert("RGB")).astype(np.int16)
    H, W = a.shape[:2]
    # 중앙 월드 영역: 가로 20~80%, 세로 15~72% (상단 바·하단 스킬바·좌측 킬피드 제외)
    c = a[int(H * .15):int(H * .72), int(W * .20):int(W * .80)]
    def sat(x):
        v = x.max(axis=2)
        return float((v - x.min(axis=2)).mean()), float(v.mean())
    s_all, _ = sat(a)
    s_c, v_c = sat(c)
    i = int(os.path.basename(p)[len(prefix):len(prefix) + 3])
    print(f"{(i-1)/10:6.1f} {s_all:8.2f} {s_c:8.2f} {v_c:8.1f}  {'#' * int(s_c)}")
