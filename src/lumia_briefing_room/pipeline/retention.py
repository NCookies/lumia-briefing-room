"""자동 정리 대상 선정. (SPEC §7.6)

무엇을 지울지(나이·개수·용량 한도, 보호 규칙) 만 다룬다. 실제로 어떻게 지우는지
(Windows 휴지통/영구 삭제)는 pipeline/delete_helper.py 가 맡는다.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from lumia_briefing_room.config import RetentionConfig

_default_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


def is_protected(meta: dict, cfg: RetentionConfig) -> bool:
    """SPEC §7.6: 고정(pin)했거나 보호 태그가 붙은 클립은 자동 정리 대상이 아니다."""
    if cfg.protect_pinned and meta.get("pinned"):
        return True
    if set(meta.get("tags", [])) & set(cfg.protect_tags):
        return True
    return False


@dataclass(frozen=True)
class _Candidate:
    meta: dict
    age_days: float
    size_bytes: int


def select_for_auto_clean(
    metas: list[dict], cfg: RetentionConfig, *, now: Callable[[], datetime] = _default_now
) -> list[dict]:
    """SPEC §7.6: maxAgeDays/maxTotalGb/maxCount 를 넘는 만큼, 보호되지 않은 것 중
    오래된 것부터 고른다. 고정·보호된 것은 지우지 않지만 개수·용량 합계에는 센다. auto_clean_enabled 가 꺼져 있거나 한도가 하나도 없으면 빈 리스트.

    호출 규약: 각 meta 는 "_created_at"(datetime) 과 "_size_bytes"(int) 를 들고 있어야
    한다 — 실제 클립 스캔 계층이 파일 mtime/크기로 채워 넣는다.
    """
    if not cfg.auto_clean_enabled:
        return []
    if cfg.max_age_days is None and cfg.max_total_gb is None and cfg.max_count is None:
        return []

    current = now()
    protected = [m for m in metas if is_protected(m, cfg)]
    candidates = [
        _Candidate(
            meta=m,
            age_days=(current - m["_created_at"]).total_seconds() / 86400,
            size_bytes=m["_size_bytes"],
        )
        for m in metas
        if not is_protected(m, cfg)
    ]
    candidates.sort(key=lambda c: c.age_days, reverse=True)  # 오래된 것부터

    selected: list[_Candidate] = []
    remaining = list(candidates)

    if cfg.max_age_days is not None:
        for c in list(remaining):
            if c.age_days > cfg.max_age_days:
                c.meta["_reason"] = "age"
                selected.append(c)
                remaining.remove(c)

    if cfg.max_count is not None:
        kept = [c for c in candidates if c not in selected]
        excess = len(kept) + len(protected) - cfg.max_count
        for c in kept:
            if excess <= 0:
                break
            if c not in selected:
                c.meta["_reason"] = "count"
                selected.append(c)
                if c in remaining:
                    remaining.remove(c)
                excess -= 1

    if cfg.max_total_gb is not None:
        max_bytes = cfg.max_total_gb * 1024**3
        kept = [c for c in candidates if c not in selected]
        total = sum(c.size_bytes for c in kept) + sum(m["_size_bytes"] for m in protected)
        for c in kept:
            if total <= max_bytes:
                break
            c.meta["_reason"] = "size"
            selected.append(c)
            total -= c.size_bytes

    order = {id(c): i for i, c in enumerate(candidates)}
    selected.sort(key=lambda c: order[id(c)])
    return [c.meta for c in selected]
