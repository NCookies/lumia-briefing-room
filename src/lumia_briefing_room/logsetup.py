"""서버·클라이언트 로그를 한 파일에 남긴다. (plan-ui.md §6)"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from lumia_briefing_room.config import _default_local_appdata

FORMAT = "%(asctime)s %(levelname)s %(message)s"
LOGGERS = ("lumia_briefing_room", "uvicorn")


def default_log_path() -> Path:
    return _default_local_appdata() / "LumiaBriefingRoom" / "logs" / "app.log"


def setup_file_logging(path: Path | None = None) -> logging.Handler:
    path = path or default_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter(FORMAT))
    for name in LOGGERS:
        logger = logging.getLogger(name)
        logger.addHandler(handler)
        if logger.level == logging.NOTSET or logger.level > logging.INFO:
            logger.setLevel(logging.INFO)
    return handler
