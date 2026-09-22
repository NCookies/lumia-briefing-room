"""일회성 조사 도구: 스킬바 R(궁극기) 칸이 준비/쿨타임 중 어느 쪽인지 판독 (SPEC §2.12 #9).

관찰: 준비 상태는 원래 아이콘 색 그대로, 쿨타임 상태는 파르스름한 반투명 오버레이가
덮이고 흰 숫자가 뜬다. "파란기 픽셀 비율"만으로 갈리는지 실측한다
(2026-09-22, 라벨된 클립 20260920_134809_01/03 프레임으로 1차 확인 — 준비 0.0 vs 쿨타임 0.27).

usage: ultimate_skill.py <clip.mp4> [t1 t2 t3 ...]   (초 단위, 생략하면 0 10 20 ... 60)
"""
import sys
import cv2
import numpy as np

R_ROI = (1110, 1290, 1170, 1360)   # x0,y0,x1,y1. 눈대중 앵커, 정밀 측정 전 값
BLUE_TINT_THRESHOLD = 0.10          # 이 이상이면 쿨타임으로 판정 (1차 관찰 0.0 vs 0.27 중간값)


def blue_tint_fraction(frame_bgr: np.ndarray) -> float:
    x0, y0, x1, y1 = R_ROI
    roi = frame_bgr[y0:y1, x0:x1, :].astype(int)
    b, g, r = roi[..., 0], roi[..., 1], roi[..., 2]
    blue_tint = (b > 120) & (b > r + 20)
    return float(blue_tint.mean())


def is_on_cooldown(frame_bgr: np.ndarray) -> bool:
    return blue_tint_fraction(frame_bgr) >= BLUE_TINT_THRESHOLD


def main():
    path = sys.argv[1]
    times = [float(t) for t in sys.argv[2:]] or list(range(0, 61, 10))
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print(f"열기 실패: {path}")
        return
    print(f"{'t(s)':>6} {'파란비율':>8} {'판정':>6}")
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            print(f"{t:6.1f} {'read실패':>8}")
            continue
        frac = blue_tint_fraction(frame)
        verdict = "쿨타임" if frac >= BLUE_TINT_THRESHOLD else "준비"
        print(f"{t:6.1f} {frac:8.3f} {verdict:>6}")


if __name__ == "__main__":
    main()
