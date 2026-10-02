"""검색 규칙 한 곳: 대소문자·공백 차이를 무시한 부분 일치. 게임 목록(`/api/games?q=`)과 클립 탭(`/api/library/search`)이 같이 쓴다.

프론트의 `frontend/src/search.ts` 가 같은 규칙을 영상 이름·스트리머 묶음 같은 화면 쪽 글자에 쓴다.
"""

from __future__ import annotations

from collections.abc import Iterable


def normalize(text: str) -> str:
    return "".join(text.split()).casefold()


def matches(text: str, needle: str) -> bool:
    wanted = normalize(needle)
    return bool(wanted) and wanted in normalize(text)


def first_match(needle: str, fields: Iterable[tuple[str, str | None]]) -> dict | None:
    """앞에서부터 처음 맞는 칸의 `{where, text}`. 사용자에게 어디서 찾았는지 한 줄로 보여 주는 재료다."""
    for where, text in fields:
        if text and matches(text, needle):
            return {"where": where, "text": text}
    return None
