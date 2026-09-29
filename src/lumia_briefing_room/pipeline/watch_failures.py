"""실시간 감시(watcher.py)가 매치를 처리하다 실패한 내역을 사용자에게 보여주기 위한 영속 상태.

`run_polling` 은 재시도 횟수를 프로세스 메모리에서만 센다(watcher.py 의 지역 변수
`failures`) - 앱을 새로고침하거나(같은 세션) 재시작해도(다음 세션) "이 매치가 실패했다"는
걸 사용자가 알아야 하는데, 메모리만으로는 화면이 그걸 볼 방법이 없다. 그래서 실패
내역만 디스크에 남기고, API 가 그걸 읽어 화면에 보여준다. "계속하기" 버튼은
`request_retry()` 로 재시도 요청을 남기고, `run_polling` 이 다음 폴링에서
`pop_retry_requests()` 로 그 요청을 읽어가 재시도 횟수 제한과 무관하게 즉시 다시 시도한다.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class WatchFailureTracker:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._records: dict[str, dict] = self._load()
        self._retry_requests: set[str] = set()

    def _load(self) -> dict[str, dict]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {r["key"]: r for r in data.get("failures", []) if "key" in r}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"failures": list(self._records.values())}
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def record_failure(self, key: str, *, match_start_utc: datetime, message: str, disk_full: bool) -> None:
        with self._lock:
            self._records[key] = {
                "key": key,
                "matchStartUtc": match_start_utc.isoformat(),
                "message": message,
                "diskFull": disk_full,
                "occurredAt": _now_iso(),
            }
            self._save()

    def record_success(self, key: str) -> None:
        with self._lock:
            if self._records.pop(key, None) is not None:
                self._save()

    def request_retry(self, key: str) -> None:
        with self._lock:
            self._retry_requests.add(key)

    def pop_retry_requests(self) -> set[str]:
        with self._lock:
            requests, self._retry_requests = self._retry_requests, set()
            return requests

    def list(self) -> list[dict]:
        with self._lock:
            return sorted(self._records.values(), key=lambda r: r["occurredAt"])
