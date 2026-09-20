"""사망 -> 관전 화면 전환을 수치로 확인한다. (SPEC 2.12 / 4단계 실측)

좌하단 초상화가 사망 후 '회색으로 변한다'가 아니라 '통째로 사라진다'는 제보를
실제 프레임으로 검증한다. 후보 ROI 들의 프레임별 통계를 표로 낸다.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROIS = {
    "portrait": (640, 1240, 870, 1440),      # SPEC 2.7 사망 검출 ROI
    "skillbar": (860, 1290, 1400, 1400),     # 스킬바 QWER
    "hpbar": (860, 1400, 1250, 1430),        # 체력바
    "rightpanel": (2150, 790, 2470, 1070),   # 관전 키 안내가 뜰 것으로 보이는 자리
    "minimap_hd": (2200, 1055, 2400, 1090),  # 미니맵 헤더 지역명
    "banner": (900, 200, 1660, 290),         # 상단 중앙 배너
}


def stats(a):
    f = a.astype(np.float32)
    mx, mn = f.max(axis=2), f.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0).mean() * 100
    return f.mean(), sat, float((f.max(axis=2) > 200).mean() * 100)


def main(seq_dir):
    paths = sorted(Path(seq_dir).glob("*.png"))
    print(f"{'frame':>6}", end="")
    for name in ROIS:
        print(f" | {name:>22}", end="")
    print("\n" + "-" * (6 + 25 * len(ROIS)))
    print(f"{'':>6}", end="")
    for _ in ROIS:
        print(f" | {'밝기':>6} {'채도':>6} {'흰%':>6}", end="")
    print()
    for p in paths:
        img = np.array(Image.open(p).convert("RGB"))
        print(f"{p.stem[-3:]:>6}", end="")
        for x0, y0, x1, y1 in ROIS.values():
            b, s, w = stats(img[y0:y1, x0:x1])
            print(f" | {b:6.1f} {s:6.1f} {w:6.1f}", end="")
        print()


if __name__ == "__main__":
    main(sys.argv[1])
