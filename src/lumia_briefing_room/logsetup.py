"""서버·클라이언트 로그를 한 파일에 남긴다. (plan-ui.md §6)"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from lumia_briefing_room.config import _default_local_appdata

FORMAT = "%(asctime)s %(levelname)s %(message)s"
LOGGERS = ("lumia_briefing_room", "uvicorn")


def default_log_path() -> Path:
    return _default_local_appdata() / "LumiaBriefingRoom" / "logs" / "app.log"


def _existing(logger: logging.Logger, kind: type, matches) -> logging.Handler | None:
    return next((h for h in logger.handlers if isinstance(h, kind) and matches(h)), None)


def setup_file_logging(path: Path | None = None) -> logging.Handler:
    """같은 파일에 핸들러를 두 번 붙이지 않는다(붙이면 모든 줄이 두 번씩 기록된다)."""
    path = path or default_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    target = str(path.resolve())
    handler = None
    for name in LOGGERS:
        logger = logging.getLogger(name)
        found = _existing(logger, RotatingFileHandler, lambda h: getattr(h, "baseFilename", None) == target)
        if found is None:
            if handler is None:
                handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
                handler.setFormatter(logging.Formatter(FORMAT))
            found = handler
            logger.addHandler(found)
        handler = handler or found
        if logger.level == logging.NOTSET or logger.level > logging.INFO:
            logger.setLevel(logging.INFO)
    return handler


def setup_outbox_logging(path: Path | None = None) -> logging.Handler:
    """ERROR 이상을 전송용 outbox 에 구조화해서 쌓는다. 전송이 꺼져 있어도 로컬에만 쌓이며 같은 파일에는 한 번만 붙인다."""
    from lumia_briefing_room.telemetry.outbox import RECENT_MAX_BYTES, Outbox, OutboxHandler, default_outbox_path

    path = Path(path) if path else default_outbox_path()
    handler = None
    for name in LOGGERS:
        logger = logging.getLogger(name)
        found = _existing(logger, OutboxHandler, lambda h: h.outbox.path == path)
        if found is None:
            recent = Outbox(path.with_name("errors_recent.jsonl"), max_bytes=RECENT_MAX_BYTES)
            handler = handler or OutboxHandler(Outbox(path), recent)
            found = handler
            logger.addHandler(found)
        handler = handler or found
    return handler
