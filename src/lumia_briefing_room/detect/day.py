from __future__ import annotations

import numpy as np

from lumia_briefing_room.detect.region import read_region

MIN_SCORE = 0.9
MIN_MARGIN = 0.04
WHITE_LO = 150


def white_score(rgb: np.ndarray) -> np.ndarray:
    """글자(흰색/크림색)만 0~1 로. 모든 채널이 밝아야 글자이므로 빨강·주황 배경은 0 이다.

    지역명처럼 max 채널을 쓰면 진한 빨강 배경(7일차 이후)이 글자로 잡혀, 템플릿이 숫자가 아니라
    배경색을 학습한다 — 실제로 6일차와 7일차가 뒤바뀌어 읽혔다.
    """
    lo = rgb.astype(np.int16).min(axis=-1)
    return np.clip((lo - WHITE_LO) / (255 - WHITE_LO), 0.0, 1.0).astype(np.float32)


def read_game_day(day_rgb: np.ndarray, templates: dict[str, np.ndarray]) -> int | None:
    """SPEC §2.10: 상단 HUD `N일 차` 의 숫자 한 글자를 읽는다.

    `일 차` 가 모든 날에 공통이라 낱말 전체를 비교하면 숫자 차이가 묻힌다 — 숫자 부분만 잘라 쓴다.
    지역명과 같은 템플릿 매칭이고, 템플릿 이름이 숫자 문자열이다. 숫자 모양(3·5·6·7·8)이 비슷해 마진 기준을
    지역명보다 낮췄다 — 대신 점수 기준을 높여(0.9) 모르는 글자를 걸러낸다.
    """
    name = read_region(
        white_score(day_rgb), templates, min_score=MIN_SCORE, min_margin=MIN_MARGIN
    ).name
    return int(name) if name is not None and name.isdigit() else None
