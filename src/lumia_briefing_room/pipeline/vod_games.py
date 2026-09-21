from __future__ import annotations

from dataclasses import dataclass

from lumia_briefing_room.detect.types import FrameState

DEFAULT_MAX_GAP_SEC = 30.0
DEFAULT_MIN_GAME_SEC = 60.0
DAY_CONFIRM_FRAMES = 5


@dataclass(frozen=True)
class GameSpan:
    index: int
    start: float
    end: float
    confidence: float


def is_ingame(state: FrameState) -> bool:
    """인게임 HUD(낮밤 아이콘·일차)가 읽히거나, 관전이 아닌 채 K 가 읽히면 게임 안이다. 로비·로딩·결과 화면은 셋 다 비어 있다."""
    return (
        state.day_night is not None
        or state.game_day is not None
        or (state.k is not None and state.spectating is False)
    )


def _runs(states: list[FrameState], max_gap_sec: float) -> list[list[FrameState]]:
    runs: list[list[FrameState]] = []
    current: list[FrameState] | None = None
    for state in states:
        if not is_ingame(state):
            continue
        if current is not None and state.t - current[-1].t <= max_gap_sec:
            current.append(state)
        else:
            current = [state]
            runs.append(current)
    return runs


def _split_points_by_day(run: list[FrameState]) -> list[int]:
    """일차가 2 이상에서 1 로 돌아가면 새 게임이다. 숫자 오독 한두 프레임에 끊기지 않도록 같은 값이 연속 확정돼야 한다."""
    splits: list[int] = []
    confirmed: int | None = None
    streak_value: int | None = None
    streak_count = 0
    streak_start = 0
    for i, state in enumerate(run):
        day = state.game_day
        if day is None:
            continue
        if day == streak_value:
            streak_count += 1
        else:
            streak_value, streak_count, streak_start = day, 1, i
        if streak_count == DAY_CONFIRM_FRAMES and day != confirmed:
            if day == 1 and confirmed is not None and confirmed >= 2:
                splits.append(streak_start)
            confirmed = day
    return splits


def split_games(
    states: list[FrameState],
    *,
    max_gap_sec: float = DEFAULT_MAX_GAP_SEC,
    min_game_sec: float = DEFAULT_MIN_GAME_SEC,
) -> list[GameSpan]:
    """프레임별 판독을 게임(1판) 구간으로 나눈다. 로그가 없는 다시보기용이다.

    인게임 프레임이 max_gap_sec 이내로 이어지면 한 게임이다(로딩·오버레이·방송 화면 전환은 메운다).
    로비 없이 붙은 두 판은 일차가 1로 돌아가는 것으로 가른다. min_game_sec 보다 짧은 구간은 게임이 아니다.
    """
    pieces: list[list[FrameState]] = []
    for run in _runs(states, max_gap_sec):
        bounds = [0, *_split_points_by_day(run), len(run)]
        pieces.extend(run[a:b] for a, b in zip(bounds, bounds[1:]))

    games: list[GameSpan] = []
    for piece in pieces:
        start, end = piece[0].t, piece[-1].t
        if end - start < min_game_sec:
            continue
        inside = states_in(states, GameSpan(0, start, end, 0.0))
        confidence = sum(is_ingame(s) for s in inside) / len(inside)
        games.append(GameSpan(index=len(games) + 1, start=start, end=end, confidence=confidence))
    return games


def states_in(states: list[FrameState], span: GameSpan) -> list[FrameState]:
    return [s for s in states if span.start <= s.t <= span.end]
