from lumia_briefing_room.config import FilterConfig
from lumia_briefing_room.detect.pvp import score_interval
from lumia_briefing_room.detect.types import CombatInterval

_PRESET_TAGS: dict[str, frozenset[str]] = {
    "won": frozenset({"kill", "assist"}),
    "lost": frozenset({"death"}),
}


def _resolve_tag_filter(cfg: FilterConfig) -> tuple[frozenset[str], frozenset[str]]:
    """SPEC §7.3: all/won/lost 는 고정 규칙, custom 만 filter.tags.* 를 본다."""
    if cfg.preset in _PRESET_TAGS:
        return _PRESET_TAGS[cfg.preset], frozenset()
    if cfg.preset == "all":
        return frozenset(), frozenset()
    return frozenset(cfg.tags.include), frozenset(cfg.tags.exclude)


def _tags_pass(tags: frozenset[str], include: frozenset[str], exclude: frozenset[str]) -> bool:
    if exclude and tags & exclude:
        return False
    if include and not (tags & include):
        return False
    return True


HARD_EVIDENCE_TAGS = frozenset({"kill", "assist", "death"})


def _phase_ok(phase: int | None, cfg: FilterConfig) -> bool:
    """SPEC §2.0: 무료 부활 = phaseIndex <= 3, 크레딧 = phaseIndex >= 4.

    특정 조건을 요청했는데 phase 를 모르면(None) 보수적으로 걸러낸다 —
    조용히 잘못 포함하는 것보다 낫다.
    """
    if cfg.phase_min is not None and (phase is None or phase < cfg.phase_min):
        return False
    if cfg.phase_max is not None and (phase is None or phase > cfg.phase_max):
        return False
    if cfg.revive_cost == "free" and (phase is None or phase > 3):
        return False
    if cfg.revive_cost == "credit" and (phase is None or phase < 4):
        return False
    return True


def apply_filter(
    intervals: list[CombatInterval],
    cfg: FilterConfig,
    *,
    game_mode: str = "any",
    phase_indices: list[int | None] | None = None,
) -> list[CombatInterval]:
    """SPEC §7.3: 생성 필터. 기본 설정(FilterConfig())이면 전부 통과한다.

    phase_indices 는 일차 판독이 아직 없어(plan.md §8-5) 호출자가 준비되기 전까지
    생략할 수 있다 — 그 경우 phase/reviveCost 관련 설정이 켜져 있으면 전부 걸러진다
    (모르는 걸 통과시키지 않는다).
    """
    include, exclude = _resolve_tag_filter(cfg)
    phases = phase_indices if phase_indices is not None else [None] * len(intervals)

    result = []
    for interval, phase in zip(intervals, phases):
        duration = interval.end - interval.start
        if (
            cfg.min_duration_sec is not None
            and duration < cfg.min_duration_sec
            and not (interval.tags & HARD_EVIDENCE_TAGS)
        ):
            continue
        if cfg.max_duration_sec is not None and duration > cfg.max_duration_sec:
            continue
        if not _tags_pass(interval.tags, include, exclude):
            continue
        if cfg.day_night != "any" and interval.day_night != cfg.day_night:
            continue
        if cfg.game_mode != "any" and game_mode != cfg.game_mode:
            continue
        if not _phase_ok(phase, cfg):
            continue
        if cfg.min_pvp_score > 0 and score_interval(interval, cfg.pvp_weights).score < cfg.min_pvp_score:
            continue
        result.append(interval)
    return result
