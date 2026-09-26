"""일별 수신 집계(건수·평균 크기·버려진/거부된 필드 이름). DB 를 정할 때의 판단 자료다.

값은 절대 남기지 않고 필드 이름과 숫자만 센다. 이름은 공격자가 만들 수 있으므로 길이·개수를 제한한다.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("receiver.stats")
MAX_NAME_LEN = 64
MAX_DISTINCT_NAMES = 200


def _bump(counter: dict, name: str, by: int = 1) -> None:
    name = name[:MAX_NAME_LEN]
    if name in counter or len(counter) < MAX_DISTINCT_NAMES:
        counter[name] = counter.get(name, 0) + by


class DailyStats:
    def __init__(self, root: Path):
        self.dir = root / "stats"
        self._lock = threading.Lock()

    def record(self, endpoint: str, size: int, *, dropped=(), rejected_fields=None) -> None:
        try:
            self._record(endpoint, size, dropped, rejected_fields)
        except Exception:
            log.exception("stats write failed")

    def _record(self, endpoint, size, dropped, rejected_fields) -> None:
        now = datetime.now(timezone.utc)
        path = self.dir / f"{now:%Y-%m-%d}.json"
        with self._lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            for key in ("requests", "bytes", "avgBytes", "rejected", "rejectedFields", "droppedFields"):
                data.setdefault(key, {})
            data["date"] = f"{now:%Y-%m-%d}"
            if rejected_fields is not None:
                _bump(data["rejected"], endpoint)
                for name in rejected_fields:
                    _bump(data["rejectedFields"], name)
            else:
                _bump(data["requests"], endpoint)
                _bump(data["bytes"], endpoint, size)
                data["avgBytes"][endpoint] = data["bytes"][endpoint] // data["requests"][endpoint]
                for name in dropped:
                    _bump(data["droppedFields"], name)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, path)
