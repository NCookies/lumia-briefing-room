"""일회성 조사 도구: 상단 HUD의 낮/밤 아이콘 색을 재
해(노랑)와 달(보라)이 색만으로 갈리는지 본다.

usage: daynight.py <session_dir> <first> <last> <step> <ffmpeg> <work_dir>
"""
import sys, os, subprocess
import numpy as np
from PIL import Image

SESSION, first, last, step, FFMPEG, WORK = (
    sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5], sys.argv[6])
os.makedirs(WORK, exist_ok=True)
mp4, png = os.path.join(WORK, "_d.mp4"), os.path.join(WORK, "_d.png")
init = open(os.path.join(SESSION, "init-stream0.m4s"), "rb").read()

ICON = (1145, 30, 1185, 58)     # 낮/밤 아이콘
DAYT = (1120, 6, 1180, 32)      # "N일 차" 텍스트

print(f"{'seg':>5} | {'노랑px':>6} {'보라px':>6} {'판정':>6} | 아이콘 평균 RGB")
for n in range(first, last + 1, step):
    src = os.path.join(SESSION, f"chunk-stream0-{n:05d}.m4s")
    if not os.path.isfile(src):
        print(f"{n:5d}  (없음)"); continue
    with open(mp4, "wb") as f:
        f.write(init); f.write(open(src, "rb").read())
    if subprocess.run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", mp4,
                       "-frames:v", "1", png], capture_output=True).returncode:
        print(f"{n:5d}  (디코딩 실패)"); continue
    a = np.array(Image.open(png).convert("RGB"))
    c = a[ICON[1]:ICON[3], ICON[0]:ICON[2]].astype(np.int16)
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    v = c.max(axis=2); s = v - c.min(axis=2)
    vivid = (v >= 90) & (s >= 55)
    yellow = vivid & (r > b + 50) & (g > b + 30)      # 해: R,G 높고 B 낮음
    purple = vivid & (b > g + 40) & (r > g + 20)      # 달: R,B 높고 G 낮음
    ny, npu = int(yellow.sum()), int(purple.sum())
    verdict = "낮" if ny > npu and ny >= 40 else ("밤" if npu > ny and npu >= 40 else "?")
    print(f"{n:5d} | {ny:6d} {npu:6d} {verdict:>6} | ({r.mean():5.1f},{g.mean():5.1f},{b.mean():5.1f})")
for p in (mp4, png):
    if os.path.exists(p):
        os.remove(p)
