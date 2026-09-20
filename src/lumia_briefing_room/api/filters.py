"""저장된 클립 메타데이터 위에서 도는 UI 필터. (plan-ui.md §2.3)

pipeline/filters.py::apply_filter() 는 검출 직후의 CombatInterval 목록에
동작하고, 이건 이미 디스크에 저장된 메타데이터 dict 위에서 동작한다 —
입력 타입이 달라 일부러 별도 모듈로 뒀다.
"""

from dataclasses import dataclass, field

from lumia_briefing_room.api.clips import ClipSummary


@dataclass(frozen=True)
class ClipQuery:
    tags: list[str] = field(default_factory=list)  # OR
    day_night: str | None = None
    game_mode: str | None = None
    pinned_only: bool = False
    trashed_only: bool = False


def filter_clip_summaries(clips: list[ClipSummary], query: ClipQuery) -> list[ClipSummary]:
    result = []
    for c in clips:
        meta = c.meta
        is_trashed = meta.get("deletedAt") is not None

        if query.trashed_only:
            if not is_trashed:
                continue
        elif is_trashed:
            continue

        if query.tags and not (set(meta.get("tags", [])) & set(query.tags)):
            continue
        if query.day_night is not None and meta.get("dayNight") != query.day_night:
            continue
        if query.game_mode is not None and meta.get("gameMode") != query.game_mode:
            continue
        if query.pinned_only and not meta.get("pinned"):
            continue

        result.append(c)
    return result
