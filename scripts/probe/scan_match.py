"""일회성 조사 도구: 매치 구간을 세그먼트 단위로 훑으며
(1) 우상단 K/A 카운터 영역, (2) 좌하단 초상화 배지 영역의 지표를 뽑는다.
프레임을 한 장씩 만들고 바로 지워 디스크를 안 쓴다. 원본은 읽기만 한다.

usage: scan_match.py <session_dir> <first> <last> <step> <ffmpeg> <work_dir>
"""
import sys, os, subprocess
import numpy as np
from PIL import Image

SESSION, first, last, step, FFMPEG, WORK = (
    sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5], sys.argv[6])
os.makedirs(WORK, exist_ok=True)
tmp_mp4, tmp_png = os.path.join(WORK, "_s.mp4"), os.path.join(WORK, "_s.png")
init = open(os.path.join(SESSION, "init-stream0.m4s"), "rb").read()

# 2560x1440 기준 ROI
K_ROI = (2452, 27, 2488, 51)          # K 값
BADGE = (660, 1380, 760, 1440)        # 초상화 좌하단 배지
FACE  = (690, 1250, 860, 1400)        # 초상화 얼굴

def stats(a, roi):
    x0, y0, x1, y1 = roi
    c = a[y0:y1, x0:x1].astype(np.int16)
    v = c.max(axis=2); s = v - c.min(axis=2)
    return s.mean(), v.mean(), int(((v >= 200) & (s <= 45)).sum())

print(f"{'seg':>5} {'K흰px':>6} | {'배지채도':>8} {'배지밝기':>8} | {'얼굴채도':>8} {'얼굴밝기':>8}")
for n in range(first, last + 1, step):
    src = os.path.join(SESSION, f"chunk-stream0-{n:05d}.m4s")
    if not os.path.isfile(src):
        print(f"{n:5d}  (없음)"); continue
    with open(tmp_mp4, "wb") as f:
        f.write(init); f.write(open(src, "rb").read())
    r = subprocess.run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", tmp_mp4,
                        "-frames:v", "1", tmp_png], capture_output=True)
    if r.returncode or not os.path.exists(tmp_png):
        print(f"{n:5d}  (디코딩 실패)"); continue
    a = np.array(Image.open(tmp_png).convert("RGB"))
    _, _, kpx = stats(a, K_ROI)
    bs, bv, _ = stats(a, BADGE)
    fs, fv, _ = stats(a, FACE)
    print(f"{n:5d} {kpx:6d} | {bs:8.2f} {bv:8.1f} | {fs:8.2f} {fv:8.1f}")
for p in (tmp_mp4, tmp_png):
    if os.path.exists(p):
        os.remove(p)
