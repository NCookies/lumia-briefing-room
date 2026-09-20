from __future__ import annotations

from dataclasses import dataclass, field

from lumia_briefing_room.detect.types import CombatInterval

ENEMY_RINGS_FULL_AT = 1.5

# enemyRings 는 0: 라벨 57개로 재보니 증거 없는 교전(8)과 사냥(21)을 못 가른다(AUC 0.53).
# 신호 자체와 enemyRingMean 은 계속 기록하고, 가중치만 뺐다.
DEFAULT_WEIGHTS = {"enemyRings": 0.0, "death": 0.9, "teammateDeath": 0.8}


@dataclass(frozen=True)
class PvpScore:
    score: float
    signals: list[str] = field(default_factory=list)


def score_interval(interval: CombatInterval, weights: dict[str, float]) -> PvpScore:
    """SPEC §2.12: 킬/어시는 1.0, 나머지 증거는 가장 센 것의 가중치.

    킬/어시는 플레이어만 카운트되므로 확실하다. 내 사망·팀원 사망은 강하지만 확실하지는 않다 —
    야생동물이나 금지구역에도 죽는다. signals 는 왜 그 점수가 나왔는지를 남긴다.
    가중치는 라벨로 검증되기 전까지 임시값이라 설정으로 뺐다.
    """
    signals: list[str] = []
    candidates: list[float] = []

    if interval.k_delta > 0:
        signals.append("kill_delta")
    if interval.a_delta > 0:
        signals.append("assist_delta")
    if signals:
        return PvpScore(score=1.0, signals=signals)

    if interval.died:
        signals.append("death")
        candidates.append(weights.get("death", 0.0))
    if interval.teammate_deaths > 0:
        signals.append("teammate_death")
        candidates.append(weights.get("teammateDeath", 0.0))

    mean = interval.enemy_ring_mean
    ring_weight = weights.get("enemyRings", 0.0)
    if mean and mean > 0 and ring_weight > 0:
        signals.append("enemy_rings")
        candidates.append(ring_weight * min(mean / ENEMY_RINGS_FULL_AT, 1.0))

    return PvpScore(score=round(max(candidates, default=0.0), 4), signals=signals)
