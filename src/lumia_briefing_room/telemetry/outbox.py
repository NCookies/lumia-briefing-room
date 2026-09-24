"""오류 로그 outbox. ERROR 이상의 로그를 로거 이름·예외 종류·스택과 함께 로컬 jsonl 에 쌓아 두었다가, 전송이 켜져 있을 때만 읽어 간다.

`app.log` 는 사람이 읽는 형식이라 로거 이름·예외 종류가 없고 트레이스백이 여러 줄로 흩어져 있어 서버 계약(`LogEntry`)을 만들기 어렵다.
outbox 는 로컬에만 있고(개인정보 제거는 보낼 때 한다), 대기분이 상한을 넘으면 오래된 것부터 버린다.
"""

from __future__ import annotations

import json
import logging
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

from lumia_briefing_room.config import _default_local_appdata

MAX_BYTES = 20 * 1024 * 1024
FIELD_MAX = 12_000
_LOCK = threading.RLock()
_OWN_LOGGERS = ("lumia_briefing_room.telemetry",)


def default_outbox_path() -> Path:
    return _default_local_appdata() / "LumiaBriefingRoom" / "outbox" / "errors.jsonl"


def entry_from_record(record: logging.LogRecord) -> dict:
    entry = {
        "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage()[:FIELD_MAX],
    }
    exc = record.exc_info
    if exc and exc[0] is not None:
        entry["exceptionType"] = exc[0].__name__
        entry["stack"] = "".join(traceback.format_exception(*exc))[-FIELD_MAX:]
    return entry


class Outbox:
    def __init__(self, path: Path, *, max_bytes: int = MAX_BYTES):
        self.path = Path(path)
        self.max_bytes = max_bytes

    def append(self, entry: dict) -> None:
        """로깅 경로에서 불리므로 어떤 실패도 밖으로 내지 않는다."""
        try:
            line = json.dumps(entry, ensure_ascii=False) + "\n"
            with _LOCK:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(line)
                if self.path.stat().st_size > self.max_bytes:
                    self._trim()
        except Exception:
            pass

    def _lines(self) -> list[str]:
        try:
            return self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []

    def _write(self, lines: list[str]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        tmp.replace(self.path)

    def _trim(self) -> None:
        lines = self._lines()
        size = sum(len(line.encode("utf-8")) + 1 for line in lines)
        target = int(self.max_bytes * 0.75)
        while lines and size > target:
            size -= len(lines.pop(0).encode("utf-8")) + 1
        self._write(lines)

    @staticmethod
    def _parse(line: str) -> dict | None:
        try:
            value = json.loads(line)
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    def read(self) -> list[dict]:
        with _LOCK:
            return [e for e in map(self._parse, self._lines()) if e is not None]

    def clear(self) -> None:
        with _LOCK:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass

    def discard_first(self, count: int) -> None:
        """보내는 데 성공한 앞쪽 count 개(읽을 수 있는 항목 기준)를 지운다. 그 뒤에 쌓인 것은 남는다."""
        if count <= 0:
            return
        with _LOCK:
            lines = self._lines()
            seen = 0
            cut = len(lines)
            for index, line in enumerate(lines):
                if self._parse(line) is not None:
                    seen += 1
                    if seen == count:
                        cut = index + 1
                        break
            try:
                self._write(lines[cut:])
            except OSError:
                pass


class OutboxHandler(logging.Handler):
    def __init__(self, outbox: Outbox):
        super().__init__(level=logging.ERROR)
        self.outbox = outbox

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(_OWN_LOGGERS):
            return
        try:
            self.outbox.append(entry_from_record(record))
        except Exception:
            pass
