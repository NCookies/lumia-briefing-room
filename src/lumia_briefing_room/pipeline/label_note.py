"""라벨 메모(`labelNote`) 정리. 텍스트만 받고 길이 상한을 둔다. (plan-deploy.md D12)"""

from __future__ import annotations

LABEL_NOTE_MAX = 500
MEMO_MAX = 5000


def normalize_label_note(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("라벨 메모는 텍스트여야 합니다")
    text = value.strip()[:LABEL_NOTE_MAX].strip()
    return text or None


def normalize_memo(value: object) -> str | None:
    """클립 메모(`memo`): 로컬 전용 개인 메모. 서버로 보내지 않는다(contract `excluded`). 줄바꿈은 그대로 두고 길이만 제한한다."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("메모는 텍스트여야 합니다")
    return value.strip()[:MEMO_MAX].strip() or None
