from __future__ import annotations

import numpy as np

from lumia_briefing_room.detect.color import channel_stats

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
