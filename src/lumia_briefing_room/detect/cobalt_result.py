from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from lumia_briefing_room.detect.ocr import TextLine, TextReader
from lumia_briefing_room.detect.region import read_region, region_score
from lumia_briefing_room.detect.result import (
    _BAR_PREFIX,
    PLACEMENT_RE,
    STAT_LABELS,
    ResultScreen,
    clean_nickname,
    parse_stats,
)
from lumia_briefing_room.profiles.models import ResolutionProfile

OUTCOME_WIN = "승리"
OUTCOME_LOSE = "패배"
TEAMMATE_ROIS = ("cobalt_teammate1", "cobalt_teammate2", "cobalt_teammate3")
MIN_SCORE = 0.85
MIN_MARGIN = 0.1


@dataclass(frozen=True)
class CobaltTeammate:
    nickname: str | None
    tk: int | None
    kills: int | None
    deaths: int | None
    assists: int | None


@dataclass(frozen=True)
class CobaltResultScreen:
    """plan.md §10 C3: 코발트 프로토콜 `PROTOCOL COMPLETE` 뒤에 나오는 승패 화면.

    배틀로얄과 달리 순위(`N/8`)가 아니라 `승리`/`패배` 텍스트고, 4인 스쿼드(본인 + 3명)다.
    """

    outcome: str
    nickname: str | None
    stats: dict
    teammates: list[CobaltTeammate]
    image: np.ndarray | None = field(default=None, compare=False, repr=False)


def read_cobalt_outcome(outcome_rgb: np.ndarray, templates: dict[str, np.ndarray]) -> str | None:
    """`승리`/`패배` 큰 글자를 읽는다.

    실측(2026-09-27, §10-1)으로 확인: 이 글꼴은 OCR 이 못 읽는다(예: `패배` -> `HAHⅡ`,
    점수 0.75 로 자신 있게 틀린다). 두 글자 중 하나로 고정된 단어라 지역명·일차·`Phase N`
    과 같은 본보기 대조(`region_score`+`read_region`)를 쓴다 - 실측 2건 교차 검증 결과 정답
    상관계수 1.0, 오답 0.39 로 마진이 넉넉하다.
    """
    return read_region(
        region_score(outcome_rgb), templates, min_score=MIN_SCORE, min_margin=MIN_MARGIN
    ).name


def _looks_like_nickname(text: str) -> bool:
    """추천 배지(`5/6`)·라벨·숫자를 걸러낸다 - 닉네임 후보만 남긴다."""
    stripped = text.strip()
    return stripped not in STAT_LABELS and not stripped.isdigit() and not PLACEMENT_RE.match(stripped)


def parse_teammate_panel(lines: list[TextLine]) -> CobaltTeammate:
    """팀원 카드 OCR 줄에서 닉네임과 `TK/K/D/A` 를 찾는다.

    닉네임은 항상 `TK/K/D/A` 라벨 줄보다 위에 있다. 카드 위쪽의 추천 배지(`5/6`)
    도 라벨보다 위라 닉네임보다 먼저 올 수 있어(y 가 더 작다), 후보 중 **라벨
    줄보다 위이면서 가장 아래(닉네임 자리)** 를 고른다. 통계 숫자가 오독돼
    글자로 나온 경우(`8`→`B`)는 라벨 줄보다 아래라 후보에서 자연히 빠진다.
    """
    stats = parse_stats(lines)
    label_lines = [l for l in lines if l.text.strip() in STAT_LABELS]
    labels_y = min((l.y for l in label_lines), default=None)
    candidates = [
        l for l in lines
        if _looks_like_nickname(l.text) and (labels_y is None or l.y < labels_y)
    ]
    nickname_line = max(candidates, key=lambda l: l.y) if candidates else None
    nickname = clean_nickname(nickname_line.text) if nickname_line else None
    return CobaltTeammate(
        nickname=nickname or None,
        tk=stats["tk"], kills=stats["kills"], deaths=stats["deaths"], assists=stats["assists"],
    )


def read_cobalt_result_screen(
    frame: np.ndarray,
    profile: ResolutionProfile,
    reader: TextReader,
    outcome_templates: dict[str, np.ndarray] | None,
) -> CobaltResultScreen | None:
    if "cobalt_result_panel" not in profile.rois or "cobalt_outcome" not in profile.rois:
        return None
    if not outcome_templates:
        return None
    outcome = read_cobalt_outcome(profile.crop(frame, "cobalt_outcome"), outcome_templates)
    if outcome is None:
        return None

    panel = profile.crop(frame, "cobalt_result_panel")
    panel_lines = reader.read(panel)
    nickname_line = next((l for l in panel_lines if _BAR_PREFIX.match(l.text)), None)
    # 배틀로얄의 read_nickname(다시 잘라 3배로 키워 재판독)은 여기선 오히려 나빴다
    # (실측: 첫 판독 "|우퓨"[0.86, 정답 "우쮸"에 근접] -> 재판독 "1早"[완전히 틀림],
    # §10-1). 첫 판독 줄을 그대로 정리해 쓴다.
    nickname = clean_nickname(nickname_line.text) if nickname_line else None

    teammates = [
        parse_teammate_panel(reader.read(profile.crop(frame, name)))
        for name in TEAMMATE_ROIS
        if name in profile.rois
    ]

    return CobaltResultScreen(
        outcome=outcome,
        nickname=nickname,
        stats=parse_stats(panel_lines),
        teammates=teammates,
        image=frame,
    )


def to_result_screen(cobalt: CobaltResultScreen) -> ResultScreen:
    """`ResultScreen`(배틀로얄) 모양으로 바꿔 기존 메타데이터·프론트엔드를 그대로 쓴다.

    코발트는 순위가 아니라 승/패라 `placement`(1=승리/2=패배)·`total`(=2)은 실제
    순위가 아니라 UI 호환용 자리표시자다 - 프론트엔드는 `outcome` 이 `승리`/`패배`
    이면 순위 대신 그 글자를 보여준다(`grouping.ts::formatMatchResult`).
    """
    return ResultScreen(
        placement=1 if cobalt.outcome == OUTCOME_WIN else 2,
        total=2,
        match_type="unknown",
        match_label="",
        outcome=cobalt.outcome,
        nickname=cobalt.nickname,
        stats=cobalt.stats,
        image=cobalt.image,
    )
