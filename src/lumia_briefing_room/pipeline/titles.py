"""자동 제목 규칙: 일차·낮/밤·지역·교전 뒤에 ` · 내 캐릭터` 를 붙인다(팀원은 게임 행에만 표시). 사용자가 직접 바꾼 제목은 건드리지 않는다."""

from __future__ import annotations

from lumia_briefing_room.pipeline.orchestrator import default_title

SEPARATOR = " · "


def characters_of(meta: dict) -> list[str]:
    return [meta["myCharacter"]] if meta.get("myCharacter") else []


def _bases(meta: dict) -> set[str]:
    day_night, region = meta.get("dayNight"), meta.get("region")
    return {default_title(day_night, region), default_title(day_night, region, meta.get("gameDay"))}


def is_auto_title(meta: dict) -> bool:
    title = meta.get("title", "")
    return any(title == base or title.startswith(base + SEPARATOR) for base in _bases(meta))


def retitle(meta: dict) -> dict:
    if not is_auto_title(meta):
        return meta
    title = default_title(meta.get("dayNight"), meta.get("region"), meta.get("gameDay"), characters_of(meta))
    return {**meta, "title": title}
