"""라벨 메모(`labelNote`) 정리. 텍스트만 받고 길이 상한을 둔다. (plan-deploy.md D12)"""

from __future__ import annotations

LABEL_NOTE_MAX = 500


def normalize_label_note(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("라벨 메모는 텍스트여야 합니다")
    text = value.strip()[:LABEL_NOTE_MAX].strip()
    return text or None
