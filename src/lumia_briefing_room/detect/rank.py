from __future__ import annotations

import numpy as np

from lumia_briefing_room.detect.region import read_region, region_score

MIN_SCORE = 0.95
MIN_MARGIN = 0.1


def read_rank_digit(rank_rgb: np.ndarray, templates: dict[str, np.ndarray]) -> int | None:
    """결과 화면의 큰 순위 숫자(`3/7` 의 3)를 본보기와 대조해 읽는다.

    이 글꼴의 일부 숫자를 OCR 이 못 읽는다(3 을 `L` 로). 본보기가 있는 숫자만 읽히고, 없는 숫자는 점수가 낮아 None 이다 -
    다른 숫자로 잘못 읽지 않는다. 글자색은 순위마다 다를 수 있어 색을 보지 않고 밝기만 쓴다.
    """
    name = read_region(region_score(rank_rgb), templates, min_score=MIN_SCORE, min_margin=MIN_MARGIN).name
    return int(name) if name is not None and name.isdigit() else None
