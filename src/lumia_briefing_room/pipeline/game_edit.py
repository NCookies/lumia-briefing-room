"""사용자가 직접 고치는 게임 정보(제목·순위·TK/K/A)와 그 잠금. (plan §2-6)

고친 결과는 `game.json` 의 `matchResultSource="manual"` 로 잠가 다시 분석·결과 소급 채우기가 덮어쓰지 않게 하고,
그 게임에서 만든 클립 메타에도 같은 값·잠금을 써서 클립 탭이 같은 결과를 보이게 한다.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

TITLE_MAX = 60
MATCH_TYPES = ("rank", "normal", "unknown")
COBALT_OUTCOMES = ("승리", "패배")
_COUNT_FIELDS = ("tk", "kills", "assists")
_OUTCOME_MAX = 20
_PLACEMENT_MAX = 99
_COUNT_MAX = 999


class GameEditError(ValueError):
    pass


def normalize_title(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise GameEditError("제목은 글자여야 합니다")
    title = value.strip()
    if len(title) > TITLE_MAX:
        raise GameEditError(f"제목은 {TITLE_MAX}자까지 쓸 수 있습니다")
    return title or None


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_result_edit(edit, *, cobalt: bool) -> dict:
    if not isinstance(edit, dict):
        raise GameEditError("결과 형식이 올바르지 않습니다")
    unknown = set(edit) - {"placement", "outcome", "matchType", *_COUNT_FIELDS}
    if unknown:
        raise GameEditError(f"고칠 수 없는 값입니다: {sorted(unknown)}")
    clean: dict = {}
    if "placement" in edit:
        value = edit["placement"]
        if value is not None and not (_is_int(value) and 1 <= value <= _PLACEMENT_MAX):
            raise GameEditError(f"순위는 1~{_PLACEMENT_MAX} 정수여야 합니다")
        clean["placement"] = value
    if "outcome" in edit:
        value = edit["outcome"]
        if value is not None and not isinstance(value, str):
            raise GameEditError("결과 문구는 글자여야 합니다")
        value = (value or "").strip() or None
        if value is not None and len(value) > _OUTCOME_MAX:
            raise GameEditError(f"결과 문구는 {_OUTCOME_MAX}자까지 쓸 수 있습니다")
        if cobalt and value is not None and value not in COBALT_OUTCOMES:
            raise GameEditError("코발트는 승리 또는 패배만 고를 수 있습니다")
        clean["outcome"] = value
    if "matchType" in edit:
        if edit["matchType"] not in MATCH_TYPES:
            raise GameEditError("일반/랭크 값이 올바르지 않습니다")
        clean["matchType"] = edit["matchType"]
    for field in _COUNT_FIELDS:
        if field in edit:
            value = edit[field]
            if value is not None and not (_is_int(value) and 0 <= value <= _COUNT_MAX):
                raise GameEditError(f"{field} 는 0~{_COUNT_MAX} 정수여야 합니다")
            clean[field] = value
    return clean


def lock_result(game: dict, edit: dict) -> None:
    """고친 값을 게임 결과에 합치고 잠근다(결과 이미지 경로 같은 나머지 값은 그대로)."""
    game["matchResult"] = {**(game.get("matchResult") or {}), **edit}
    game["matchResultSource"] = "manual"


def carry_user_fields(old: dict, new: dict) -> None:
    """다시 만든 게임 기록(`new`, 제자리에서 고친다)에 옛 기록의 사용자 상태(고정·제목·잠근 결과)를 잇는다."""
    if old.get("pinned"):
        new["pinned"] = True
    if old.get("title"):
        new["title"] = old["title"]
    if old.get("matchResultSource") == "manual" and old.get("matchResult") is not None:
        new["matchResult"], new["matchResultSource"] = old["matchResult"], "manual"


def sync_clip_results(paths: Iterable[Path], edit: dict | None, *, locked: bool) -> None:
    """게임의 클립 메타에 같은 결과·잠금을 쓴다. 클립이 가진 결과 이미지 경로는 건드리지 않는다.

    `edit` 가 없으면 잠금만 바꾼다(해제). 읽거나 쓸 수 없는 클립은 건너뛴다."""
    for path in paths:
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict):
            continue
        if edit is not None:
            meta["matchResult"] = {**(meta.get("matchResult") or {}), **edit}
        if locked:
            meta["matchResultSource"] = "manual"
        elif meta.get("matchResultSource") == "manual":
            meta["matchResultSource"] = None
        try:
            path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            continue
