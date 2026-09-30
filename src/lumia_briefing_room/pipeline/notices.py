"""화면 배너와 트레이 알림으로 알릴 앱 알림(저장 공간 부족, 풀영상 실패 등). 메모리에만 둔다. (plan-fullvideo.md §3.4)"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone

log = logging.getLogger(__name__)

Notifier = Callable[[str, str], None]  # (제목, 내용)


class NoticeCenter:
    def __init__(self, notifier: Notifier | None = None) -> None:
        self._lock = threading.Lock()
        self._notices: dict[str, dict] = {}
        self._notifier = notifier

    def set_notifier(self, notifier: Notifier | None) -> None:
        self._notifier = notifier

    def post(self, kind: str, message: str, *, title: str = "루미아 브리핑룸") -> None:
        """같은 종류에 같은 내용이면 다시 알리지 않는다. 내용이 바뀌면(남은 공간 등) 새로 알린다."""
        with self._lock:
            current = self._notices.get(kind)
            if current is not None and current["message"] == message:
                return
            self._notices[kind] = {
                "kind": kind,
                "message": message,
                "title": title,
                "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            notifier = self._notifier
        if notifier is not None:
            try:
                notifier(title, message)
            except Exception:
                log.exception("알림을 띄우지 못했다")

    def clear(self, kind: str) -> None:
        with self._lock:
            self._notices.pop(kind, None)

    def list(self) -> list[dict]:
        with self._lock:
            return list(self._notices.values())


notices = NoticeCenter()
