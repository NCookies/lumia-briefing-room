from __future__ import annotations

from dataclasses import dataclass, field

from lumia_briefing_room.detect.types import CombatInterval

ENEMY_RINGS_FULL_AT = 1.5


@dataclass(frozen=True)
class PvpScore:
    score: float
    signals: list[str] = field(default_factory=list)


def score_interval(interval: CombatInterval, weights: dict[str, float]) -> PvpScore:
    """SPEC §2.12: 확정 증거가 하나라도 있으면 1.0, 없으면 추정 증거의 가중합.

    signals 는 왜 그 점수가 나왔는지를 남긴다 — 점수만 있으면 오판을 복기할 수 없다.
    가중치는 라벨로 검증되기 전까지 임시값이라 설정으로 뺐다.
    """
    confirmed = []
    if interval.k_delta > 0:
        confirmed.append("kill_delta")
    if interval.a_delta > 0:
        confirmed.append("assist_delta")
    if interval.died:
        confirmed.append("death")
    if interval.teammate_deaths > 0:
        confirmed.append("teammate_death")
    if confirmed:
        return PvpScore(score=1.0, signals=confirmed)

    mean = interval.enemy_ring_mean
    if mean and mean > 0:
        weight = weights.get("enemyRings", 0.0)
        return PvpScore(
            score=round(weight * min(mean / ENEMY_RINGS_FULL_AT, 1.0), 4),
            signals=["enemy_rings"],
        )
    return PvpScore(score=0.0)
