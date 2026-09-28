from __future__ import annotations

import numpy as np

from lumia_briefing_room.detect.region import read_region, region_score

# region_score 기본 v_lo=170 은 지역명 경고색(주황) 기준이라 `Phase N` 의 옅은 주황(밝기
# 채널이 최대 ~200)에는 너무 높다 - 실측(치지직 다시보기, plan.md §10-1)으로 120 을 확인:
# 800x600(원본 32x18) 크롭 16장 교차 검증에서 v_lo=170 은 점수가 거의 0 으로 죽어 본보기가
# 한 칸으로 뭉개졌고, 120 으로는 올바른 숫자가 항상 최고점(margin 0.02 이상)이었다.
V_LO = 120
MIN_SCORE = 0.9
MIN_MARGIN = 0.03


def read_cobalt_phase(phase_rgb: np.ndarray, templates: dict[str, np.ndarray]) -> int | None:
    """SPEC §2.9 / plan.md §10-1: 코발트 프로토콜 상단 `Phase N` 의 숫자를 읽는다.

    글자가 주황색이다(§2.10 지역명이 금지구역 예정일 때와 같은 색). day.py 의
    `white_score` 는 흰 글자만 잡아서 못 쓰고, 색과 무관한 `region_score`(밝기 대비)를 쓴다.
    """
    name = read_region(
        region_score(phase_rgb, v_lo=V_LO), templates, min_score=MIN_SCORE, min_margin=MIN_MARGIN
    ).name
    return int(name) if name is not None and name.isdigit() else None
