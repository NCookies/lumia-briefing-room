from __future__ import annotations

from dataclasses import dataclass

from lumia_briefing_room.detect.match import finalize_match
from lumia_briefing_room.detect.types import FrameState, MatchDetection
from lumia_briefing_room.pipeline.vod_games import GameSpan, states_in


@dataclass(frozen=True)
class GameDetection:
    span: GameSpan
    detection: MatchDetection


def detect_games(states: list[FrameState], spans: list[GameSpan]) -> list[GameDetection]:
    """게임마다 따로 교전 구간·태그를 만든다.

    영상 한 편에는 여러 판이 들어 있고 K/A 는 판마다 0 에서 다시 시작한다. 카운터 단조 규칙, 최종값,
    팀원 신호 포화 판정, 사망 구간이 전부 판 안에서만 성립하므로 finalize_match 는 게임 하나씩 돌린다.
    """
    return [
        GameDetection(span=span, detection=finalize_match(states_in(states, span)))
        for span in spans
    ]
