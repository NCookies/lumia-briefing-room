"""첫 실행 화면의 항목과 버전. (plan-deploy.md D3, SPEC §7.11)

항목을 추가할 때 `since` 를 새 버전으로 두면, 이전 버전까지 답한 사용자에게 그 항목만 다시 묻는다.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ConsentItem:
    key: str
    since: int


CONSENT_ITEMS: tuple[ConsentItem, ...] = (ConsentItem("setup", 1),)
CONSENT_VERSION = max(item.since for item in CONSENT_ITEMS)


def pending_items(answered_version: int, items: tuple[ConsentItem, ...] = CONSENT_ITEMS) -> list[ConsentItem]:
    return [item for item in items if item.since > answered_version]


def needs_first_run(answered_version: int, items: tuple[ConsentItem, ...] = CONSENT_ITEMS) -> bool:
    return bool(pending_items(answered_version, items))
