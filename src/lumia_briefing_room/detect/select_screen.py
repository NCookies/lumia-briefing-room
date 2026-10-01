from __future__ import annotations

import base64
import zlib
from typing import TYPE_CHECKING

import numpy as np

from lumia_briefing_room.detect.color import channel_stats

if TYPE_CHECKING:
    from lumia_briefing_room.profiles.models import ResolutionProfile

# 캐릭터 선택·루트 선택 화면은 같은 머리띠를 쓴다: 좌상단 `PAGEn 캐릭터/루트 선택`(어두운 바탕 위 회색 글자),
# 상단 가운데 시안색 남은 시간 숫자. 실측 2560x1440 스팀 녹화 2026-09-30, 세션 899프레임에서 오탐 0.
TIMER_CYAN_MIN = 0.05
TITLE_BRIGHT_RANGE = (0.09, 0.20)
TITLE_MEAN_RANGE = (40.0, 65.0)


def read_select_screen(timer_rgb: np.ndarray, title_rgb: np.ndarray) -> bool:
    t = channel_stats(timer_rgb)
    cyan = float(((t.b > 170) & (t.g > 140) & (t.r < 100)).mean())
    if cyan < TIMER_CYAN_MIN:
        return False
    s = channel_stats(title_rgb)
    bright = float(((s.v > 110) & (s.s < 45)).mean())
    mean = float(s.v.mean())
    return (
        TITLE_BRIGHT_RANGE[0] <= bright <= TITLE_BRIGHT_RANGE[1]
        and TITLE_MEAN_RANGE[0] <= mean <= TITLE_MEAN_RANGE[1]
    )


# 아래쪽 팀원 카드 3장 밑의 팀 색 막대(파랑·초록·노랑 등, 칸마다 색이 다르다). 캐릭터·루트 선택 두 페이지에 다 있고,
# 방송 화면에서 왼쪽 위를 다른 창이 덮어 머리띠가 가려져도 보인다. ROI 는 막대(위 40%) + 그 아래 무채색 카드 바깥(나머지).
# 실측 1080p 치지직 2026-10-01: 막대 6px 는 항상 100%, 바로 아래는 0%.
CARD_BAR_FRACTION = 0.4
CARD_BELOW_FROM = 0.47
CARD_VIVID_V_MIN = 120
CARD_VIVID_CHROMA_MIN = 60
CARD_BAR_MIN = 0.8
CARD_BELOW_MAX = 0.1


def _card_bar(card_rgb: np.ndarray) -> bool:
    s = channel_stats(card_rgb)
    vivid = (s.v >= CARD_VIVID_V_MIN) & (s.s >= CARD_VIVID_CHROMA_MIN)
    h = vivid.shape[0]
    bar = vivid[: max(1, int(h * CARD_BAR_FRACTION))]
    below = vivid[int(round(h * CARD_BELOW_FROM)) :]
    return float(bar.mean()) >= CARD_BAR_MIN and (below.size == 0 or float(below.mean()) <= CARD_BELOW_MAX)


def read_select_cards(cards_rgb: list[np.ndarray]) -> bool:
    """팀원 카드 3장 모두 밑에 얇은 팀 색 막대가 있으면 선택 화면이다(머리띠가 가려진 방송 화면용)."""
    return len(cards_rgb) == 3 and all(_card_bar(c) for c in cards_rgb)


SELECT_CARD_ROIS = ("select_card1", "select_card2", "select_card3")


def is_select_screen(frame: np.ndarray, profile: "ResolutionProfile") -> bool | None:
    """머리띠가 보이거나, 머리띠가 가려졌어도 팀원 카드 막대가 보이면 선택 화면. 프로필에 선택 화면 칸이 없으면 None."""
    if "select_timer" not in profile.rois or "select_title" not in profile.rois:
        return None
    if read_select_screen(profile.crop(frame, "select_timer"), profile.crop(frame, "select_title")):
        return True
    if all(name in profile.rois for name in SELECT_CARD_ROIS):
        return read_select_cards([profile.crop(frame, name) for name in SELECT_CARD_ROIS])
    return False


# 상단 가운데 모드 글자(`NORMAL GAME`/`RANK GAME`/`PRACTICE`)의 밝은 하늘색 글자 마스크. 연습 모드의 `PRACTICE` 를 기준으로 삼는다.
# 실측 2560x1440(ROI select_mode 190x24): 연습 IoU 0.985~1.0, `NORMAL GAME` 0.14~0.15.
PRACTICE_MASK_SHAPE = (24, 190)
PRACTICE_IOU_MIN = 0.6
_PRACTICE_MASK_B64 = (
    "eNq9zjEKwkAQheG3jCwWA9tuIeQKa2ch5CrjSdwQyHk8wgZBr6E3SGkRMooR3WBanWbgFR8/8Nsru/3FQc96cn15++x61bQlLQZf"
    "dnp5z2QaMgcPwi5RxrD1bEXApgFne/AS1lVEsB4h29MuprN9fC9ImPDETz5SnPCrZRh510/rpR35TcZrq6ZqvnlYdsOLz+vhQ3mb"
    "qYdIWs/Um6rGaY4nT64niB415jzLoujY1OoG/OnuDrRBfg=="
)


def _practice_mask() -> np.ndarray:
    packed = np.frombuffer(zlib.decompress(base64.b64decode(_PRACTICE_MASK_B64)), dtype=np.uint8)
    h, w = PRACTICE_MASK_SHAPE
    return np.unpackbits(packed)[: h * w].reshape(h, w).astype(bool)


def _resize_nearest(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    ys = (np.arange(shape[0]) * mask.shape[0] / shape[0]).astype(int)
    xs = (np.arange(shape[1]) * mask.shape[1] / shape[1]).astype(int)
    return mask[np.ix_(ys, xs)]


def read_practice_mode(mode_rgb: np.ndarray) -> bool:
    s = channel_stats(mode_rgb)
    mask = (s.b > 200) & (s.g > 190) & (s.r > 90)
    if mask.shape != PRACTICE_MASK_SHAPE:
        mask = _resize_nearest(mask, PRACTICE_MASK_SHAPE)
    ref = _practice_mask()
    union = int((mask | ref).sum())
    return bool(union > 0 and (mask & ref).sum() / union >= PRACTICE_IOU_MIN)
