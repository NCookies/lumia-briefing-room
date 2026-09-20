"""미니맵 아이콘 링 색으로 적/아군을 가를 수 있는지 확인. (SPEC 4단계)

제보: 노랑·초록·파랑 = 아군, 빨강 = 적. 캐릭터 선택 화면에서 팀원 3명이
파랑/초록/노랑 바를 갖는 것과 일치한다.

확정 PvP 클립(사망·킬)과 사냥 후보 클립에서 빨강 링 개수를 비교한다.
두 분포가 겹치면 이 신호는 못 쓴다.
"""
import subprocess, sys, tempfile
from pathlib import Path

import cv2
import numpy as np

MM = (2215, 1115, 2555, 1425)
ALLY = {"노랑", "초록", "하늘", "파랑"}


def hue_name(h):
    return ("빨강" if h < 15 or h >= 345 else "주황" if h < 45 else "노랑" if h < 70
            else "초록" if h < 165 else "하늘" if h < 200 else "파랑" if h < 260 else "보라")


def count_rings(frame):
    mm = frame[MM[1]:MM[3], MM[0]:MM[2]]
    g = cv2.cvtColor(mm, cv2.COLOR_BGR2GRAY)
    circles = cv2.HoughCircles(cv2.medianBlur(g, 3), cv2.HOUGH_GRADIENT, dp=1, minDist=10,
                               param1=100, param2=18, minRadius=7, maxRadius=16)
    if circles is None:
        return 0, 0
    hsv = cv2.cvtColor(mm, cv2.COLOR_BGR2HSV)
    enemy = ally = 0
    for x, y, r in np.uint16(np.around(circles))[0]:
        mask = np.zeros(g.shape, np.uint8)
        cv2.circle(mask, (int(x), int(y)), int(r), 255, 2)
        px = hsv[mask > 0]
        px = px[(px[:, 1] > 110) & (px[:, 2] > 110)]
        if len(px) < 25:
            continue
        n = hue_name(int(np.median(px[:, 0])) * 2)
        if n == "빨강":
            enemy += 1
        elif n in ALLY:
            ally += 1
    return enemy, ally


def scan(ffmpeg, clip, step=3):
    with tempfile.TemporaryDirectory() as td:
        subprocess.run([ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(clip),
                        "-vf", f"fps=1/{step}", "-y", str(Path(td) / "f_%03d.png")], check=True)
        rows = [count_rings(cv2.imread(str(p))) for p in sorted(Path(td).glob("*.png"))]
    return rows


if __name__ == "__main__":
    ff, group = sys.argv[1], sys.argv[2]
    for name in sys.argv[3:]:
        clip = Path.home() / "Videos/LumiaBriefingRoom/clips" / f"{name}.mp4"
        rows = scan(ff, clip)
        e = [r[0] for r in rows]; a = [r[1] for r in rows]
        frac = sum(1 for v in e if v > 0) / max(len(e), 1) * 100
        print(f"{group:>6} {name} | 프레임 {len(e):2d} | 적링 최대 {max(e) if e else 0} "
              f"평균 {np.mean(e) if e else 0:.1f} | 적링>0 프레임 {frac:5.1f}% | 아군링 평균 {np.mean(a) if a else 0:.1f}")
