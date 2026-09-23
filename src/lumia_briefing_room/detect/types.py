from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FrameState:
    """세그먼트 하나에서 읽은 프레임별 원시 판독값. (plan.md §4)

    combat/day_night 은 None 이면 판독 불가(로비·암전 등)다.
    face_value/face_sat 은 사망 검출을 위해 매치 전체를 모아 나중에 판단한다.
    """

    t: float
    combat: bool | None
    face_value: float | None
    face_sat: float | None
    k: int | None
    a: int | None
    day_night: str | None
    spectating: bool | None = None
    dead_teammates: tuple[int, ...] | None = None
    region: str | None = None
    enemy_rings: int | None = None
    game_day: int | None = None
    team_combat: bool | None = None
    ally_rings: int | None = None
    clock_zero: bool | None = None
    ultimate_blue: float | None = None
    ultimate_locked: bool | None = None
    tk: int | None = None


@dataclass(frozen=True)
class CombatInterval:
    start: float
    end: float
    tags: frozenset[str]
    k_delta: int
    a_delta: int
    died: bool
    day_night: str | None
    confidence: float
    teammate_deaths: int = 0
    region: str | None = None
    enemy_ring_mean: float | None = None
    game_day: int | None = None
    ultimate_delta: float | None = None
    team_combat_unreliable: bool = False


@dataclass(frozen=True)
class MatchDetection:
    intervals: list[CombatInterval]
    k_final: int | None
    a_final: int | None
    gaps: list[tuple[float, float]]
    source_incomplete: bool
    spectator_ranges: list[tuple[float, float]] = field(default_factory=list)
    teammate_deaths: list[tuple[float, int]] = field(default_factory=list)
