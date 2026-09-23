from __future__ import annotations

from dataclasses import dataclass, field

from lumia_briefing_room.detect.types import CombatInterval

ENEMY_RINGS_FULL_AT = 1.5

# 궁극기(R) 쿨타임 진입 델타(detect/ultimate.py) 임계. 이 이상이면 "궁을 썼다"로 본다.
ULTIMATE_DELTA_THRESHOLD = 0.25

# enemyRings 는 0: 라벨 57개로 재보니 증거 없는 교전(8)과 사냥(21)을 못 가른다(AUC 0.53).
# teammateDeathSplit: 1~2일차는 무료 부활이라 팀원이 흩어져 사냥하다 혼자 죽는다(스플릿). 그 날의 팀원 사망은 덜 믿는다.
# ultimateUsed: 라벨 110개(pvp 73/pve 37)로 재보니 AUC(delta) 0.914 로 강하게 갈린다(pvp 90%/pve 27% 검출,
# scripts/probe/eval_ultimate_signal.py). 사망(0.9)·팀원 사망(0.8)보다는 낮게, 미니맵(0)보다는 훨씬 높게 잡았다 -
# 야생동물·보스전에도 궁을 쓸 수 있어(pve 27%) 확정 증거는 아니지만, 지금까지의 어떤 추정 증거보다 세다.
# 2026-09-24 라벨 276개로 재조정: 킬·어시·사망 없는 클립에서 델타 0.15~0.25 는 교전 3 : 사냥 9(25%),
# 0.25 이상은 16 : 4(80%) 라 임계를 0.15->0.25, 가중치를 0.6->0.75 로 올렸다(plan-pvp.md §2.10).
# 신호 자체는 계속 기록하고, 임계·가중치는 다음 라벨 라운드에서 더 조정한다.
FREE_REVIVE_LAST_DAY = 2
DEFAULT_WEIGHTS = {
    "enemyRings": 0.0, "death": 0.9, "teammateDeath": 0.8, "teammateDeathSplit": 0.5, "ultimateUsed": 0.75,
}


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
        key = "teammateDeath"
        if interval.game_day is not None and interval.game_day <= FREE_REVIVE_LAST_DAY and "teammateDeathSplit" in weights:
            key = "teammateDeathSplit"
        candidates.append(weights.get(key, 0.0))

    mean = interval.enemy_ring_mean
    ring_weight = weights.get("enemyRings", 0.0)
    if mean and mean > 0 and ring_weight > 0:
        signals.append("enemy_rings")
        candidates.append(ring_weight * min(mean / ENEMY_RINGS_FULL_AT, 1.0))

    if interval.ultimate_delta is not None and interval.ultimate_delta >= ULTIMATE_DELTA_THRESHOLD:
        signals.append("ultimate_used")
        candidates.append(weights.get("ultimateUsed", 0.0))

    return PvpScore(score=round(max(candidates, default=0.0), 4), signals=signals)
