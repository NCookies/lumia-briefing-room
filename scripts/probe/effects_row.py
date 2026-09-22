"""일회성 조사 도구: 화면 최상단 버프/효과 아이콘 줄 개수 세기 (SPEC §2.12 #10).

날씨(해/바람) 박스가 화면 고정 위치(2560x1440 기준 대략 x 970..1090)에 항상 떠 있고,
활성 효과 아이콘은 그 왼쪽에 슬롯 단위로 이어 붙는다는 게 1차 육안 관찰이었다.

★ 미완성 — 단순 규칙으로는 안 됨 (2026-09-22 실측).
슬롯 하단의 얇은 시안색 밑줄(진행바)로 세려 했으나, **밑줄 폭이 버프 종류마다 다르다.**
실측: 같은 방식으로 잰 두 사례에서 한쪽은 아이콘당 밑줄 폭 64px(사냥 클립, 방금 막 생긴 버프로
추정), 다른 쪽은 16px(교전 클립, 오래 지속된 버프로 추정 — 밑줄이 시간 경과에 따라 옅어지거나
줄어드는 것으로 보인다)였다. 고정 슬롯 폭 가정이 깨지므로 gap 기반 체이닝만으로는
오탐/누락이 둘 다 난다(사냥 라벨 클립에서 화면 왼쪽의 무관한 레벨/경험치 진행바까지
끌어들여 9개로 오검출된 사례 있음).

**다음에 시도할 것** (아직 안 함): 밑줄이 아니라 아이콘 자체의 사각 테두리/배경 패널을
찾는 방식(고정 크기 사각형 템플릿 매칭 또는 테두리 색 검출)으로 바꾸는 것. 지금 버전은
참고용 초안이며 라벨 대조에 쓰지 않는다.

usage: effects_row.py <clip.mp4> [t1 t2 t3 ...]   (초 단위, 생략하면 0 10 20 30 40 50 60)
"""
import sys
import cv2
import numpy as np

WEATHER_BOX_LEFT = 970   # 눈대중 앵커. 정밀 측정 전 값
UNDERLINE_Y = (57, 65)   # 슬롯 밑줄이 걸리는 y 대역 (2560x1440 기준)
SCAN_X_MIN = 550         # 이 이전은 안 본다 (레벨바 등 무관 위젯 배제)
SLOT_GAP = 25            # 슬롯 사이 허용 간격(px). 이보다 크게 끊기면 그 뒤는 안 셈


def count_effect_icons(frame_bgr: np.ndarray) -> int:
    """★ 미완성 — 위 docstring 참고. 밑줄 폭이 일정하다는 가정이 실측으로 깨졌다."""
    band = frame_bgr[UNDERLINE_Y[0]:UNDERLINE_Y[1], SCAN_X_MIN:WEATHER_BOX_LEFT, :].astype(int)
    b, g, r = band[..., 0], band[..., 1], band[..., 2]
    bright = (g > 120) & (b > 120) & (r + g + b > 350)
    col_bright = bright.any(axis=0)  # index 0 == SCAN_X_MIN

    segments = []
    in_seg = False
    start = 0
    for i, v in enumerate(col_bright):
        if v and not in_seg:
            in_seg, start = True, i
        elif not v and in_seg:
            segments.append((start, i - 1))
            in_seg = False
    if in_seg:
        segments.append((start, len(col_bright) - 1))

    # 가상 앵커(날씨 박스 왼쪽 끝, SCAN_X_MIN 기준 상대좌표)에서부터 왼쪽으로 체이닝.
    anchor = WEATHER_BOX_LEFT - SCAN_X_MIN
    segments.sort(key=lambda s: -s[1])
    count = 0
    pos = anchor
    for s, e in segments:
        if pos - e > SLOT_GAP:
            break
        count += 1
        pos = s
    return count


def main():
    path = sys.argv[1]
    times = [float(t) for t in sys.argv[2:]] or [0, 10, 20, 30, 40, 50, 60]
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print(f"열기 실패: {path}")
        return
    print(f"{'t(s)':>6} {'효과개수(미완성)':>12}")
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            print(f"{t:6.1f} {'read실패':>12}")
            continue
        n = count_effect_icons(frame)
        print(f"{t:6.1f} {n:12d}")


if __name__ == "__main__":
    main()
