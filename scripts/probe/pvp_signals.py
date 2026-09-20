"""PvP 판별용 새 신호들의 실현 가능성 확인. (SPEC 4단계)

측정 대상:
  - 스킬바 빨간 X (내 사망/무력화 추정)
  - 팀 패널 슬롯별 사망 표시
  - 미니맵 캐릭터 아이콘 링 색상 (아군/적 구분 가능한지)
  - 미니맵 헤더 지역명 텍스트 (글자 픽셀이 잡히는지)
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SKILLBAR = (880, 1290, 1300, 1365)
PORTRAIT = (720, 1270, 860, 1400)
TEAM1 = (2085, 1120, 2205, 1260)
TEAM2 = (2085, 1260, 2205, 1400)
MINIMAP = (2215, 1115, 2555, 1425)
REGION = (2130, 1082, 2405, 1114)


def red_ratio(a):
    f = a.astype(np.int16)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    return float(((r > 120) & (r - g > 60) & (r - b > 60)).mean() * 100)


def text_ratio(a):
    """글자다움: 밝고 배경 대비가 큰 픽셀 비율."""
    f = a.astype(np.float32)
    return float((f.max(axis=2) > 140).mean() * 100)


def ring_hues(a):
    """채도 높은 픽셀의 색상(hue) 히스토그램 — 링 색이 갈리는지 본다."""
    f = a.astype(np.float32) / 255
    mx, mn = f.max(axis=2), f.min(axis=2)
    sat, val = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0), mx
    m = (sat > 0.55) & (val > 0.45)
    if m.sum() < 30:
        return {}
    r, g, b = f[..., 0][m], f[..., 1][m], f[..., 2][m]
    mxm, mnm = np.maximum.reduce([r, g, b]), np.minimum.reduce([r, g, b])
    d = np.maximum(mxm - mnm, 1e-6)
    h = np.where(mxm == r, ((g - b) / d) % 6, np.where(mxm == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    names = {"빨강": ((h < 15) | (h >= 345)), "주황": ((h >= 15) & (h < 45)),
             "노랑": ((h >= 45) & (h < 70)), "초록": ((h >= 70) & (h < 165)),
             "하늘": ((h >= 165) & (h < 200)), "파랑": ((h >= 200) & (h < 260)),
             "보라": ((h >= 260) & (h < 345))}
    return {k: int(v.sum()) for k, v in names.items() if v.sum() > 25}


def main(seq_dir):
    print(f"{'f':>4} {'스킬X%':>7} {'초상빨강%':>9} {'팀1빨강%':>8} {'팀2빨강%':>8} {'지역글자%':>9}  미니맵 링 색상")
    for p in sorted(Path(seq_dir).glob("*.png")):
        im = np.array(Image.open(p).convert("RGB"))
        c = lambda r: im[r[1]:r[3], r[0]:r[2]]
        hues = ring_hues(c(MINIMAP))
        top = ", ".join(f"{k}:{v}" for k, v in sorted(hues.items(), key=lambda x: -x[1])[:5])
        print(f"{p.stem[-3:]:>4} {red_ratio(c(SKILLBAR)):7.1f} {red_ratio(c(PORTRAIT)):9.1f} "
              f"{red_ratio(c(TEAM1)):8.1f} {red_ratio(c(TEAM2)):8.1f} {text_ratio(c(REGION)):9.1f}  {top}")


if __name__ == "__main__":
    main(sys.argv[1])
