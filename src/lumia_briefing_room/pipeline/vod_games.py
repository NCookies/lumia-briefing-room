from __future__ import annotations

from dataclasses import dataclass

from lumia_briefing_room.detect.types import FrameState

DEFAULT_MAX_GAP_SEC = 30.0
DEFAULT_MIN_GAME_SEC = 60.0
DAY_CONFIRM_FRAMES = 5
SELECT_MAX_BEFORE_GAME_SEC = 150.0
SELECT_MAX_GAP_SEC = 15.0


@dataclass(frozen=True)
class GameSpan:
    index: int
    start: float
    end: float
    confidence: float
    select_start: float | None = None
    practice: bool = False


def is_ingame(state: FrameState) -> bool:
    """인게임 HUD(낮밤 아이콘·일차·코발트 Phase)가 읽히거나, 관전이 아닌 채 K 가 읽히면 게임 안이다.

    로비·로딩·결과 화면은 전부 비어 있다. `cobalt_phase`(plan.md §10 C2)는 배틀로얄의
    `game_day` 와 같은 역할을 코발트 프로토콜에서 한다 - 이 스트리머의 다시보기에서는
    `k`/`spectating` 판독이 UI 스케일 차이로 신뢰할 수 없었는데(plan-vod.md §8-4), Phase
    판독은 이 문제와 무관해 독립적인 신호로 쓸 수 있다(§10-1·§10-2).
    """
    return (
        state.day_night is not None
        or state.game_day is not None
        or state.cobalt_phase is not None
        or (state.k is not None and state.spectating is False)
    )


def _strong_ingame(state: FrameState) -> bool:
    """낮/밤 아이콘만으로는 약하다 - 로비 그림이 아이콘으로 읽히는 프레임이 있다(2026-10-01 치지직 1080p)."""
    return (
        state.game_day is not None
        or state.cobalt_phase is not None
        or (state.k is not None and state.spectating is False)
    )


def _trim_weak_tail(piece: list[FrameState]) -> list[FrameState]:
    """게임 끝은 확실한 인게임 신호가 마지막으로 읽힌 프레임이다. 그런 프레임이 하나도 없으면 그대로 둔다.

    결과 탐색이 게임 끝 뒤부터라, 결과 화면 뒤 로비가 아이콘으로 잘못 읽혀 끝이 늘어나면 결과 화면을 지나친다.
    """
    last = next((i for i in range(len(piece) - 1, -1, -1) if _strong_ingame(piece[i])), None)
    return piece if last is None else piece[: last + 1]


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
        pieces.extend(_trim_weak_tail(run[a:b]) for a, b in zip(bounds, bounds[1:]))

    games: list[GameSpan] = []
    prev_end = float("-inf")
    for piece in pieces:
        start, end = piece[0].t, piece[-1].t
        if end - start < min_game_sec:
            continue
        inside = states_in(states, GameSpan(0, start, end, 0.0))
        confidence = sum(is_ingame(s) for s in inside) / len(inside)
        select_start, practice = selection_before(states, start, floor=prev_end)
        games.append(
            GameSpan(
                index=len(games) + 1, start=start, end=end, confidence=confidence,
                select_start=select_start, practice=practice,
            )
        )
        prev_end = end
    return games


def selection_before(states: list[FrameState], game_start: float, *, floor: float) -> tuple[float | None, bool]:
    """게임 바로 앞의 캐릭터·루트 선택 화면 덩어리의 (첫 프레임, 연습 모드 여부). 뒤에 게임이 이어지지 않는 덩어리(닷지)는 여기 닿지 않는다."""
    lo = max(game_start - SELECT_MAX_BEFORE_GAME_SEC, floor)
    frames = [s for s in states if s.select_screen and lo < s.t < game_start]
    if not frames:
        return None, False
    cluster = [frames[-1]]
    for s in reversed(frames[:-1]):
        if cluster[-1].t - s.t > SELECT_MAX_GAP_SEC:
            break
        cluster.append(s)
    practice = sum(1 for s in cluster if s.select_practice) * 2 > len(cluster)
    return cluster[-1].t, practice


def states_in(states: list[FrameState], span: GameSpan) -> list[FrameState]:
    return [s for s in states if span.start <= s.t <= span.end]
