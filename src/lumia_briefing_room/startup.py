"""콘솔 없는 빌드(`--noconsole`)에서도 로그와 예외가 사라지지 않게 한다. (plan-deploy.md D5)

빌드본에서는 `sys.stderr` 가 `None` 이라 `logging.basicConfig()` 의 스트림 핸들러가 무의미하고,
처리되지 않은 예외는 아무 데도 남지 않는다. 그래서 파일 로그를 진실로 두고 예외 훅을 건다.
"""

import logging
import sys
import threading
from pathlib import Path

from lumia_briefing_room.logsetup import FORMAT, default_log_path, setup_file_logging

log = logging.getLogger("lumia_briefing_room.startup")

_UNSET = object()
_log_dir: Path | None = None


def console_logging_wanted(stderr=_UNSET) -> bool:
    """콘솔 없는 빌드에서는 stderr 가 None 이다. pythonw.exe 도 같다."""
    stream = sys.stderr if stderr is _UNSET else stderr
    return stream is not None and hasattr(stream, "write")


def setup_logging(*, log_path: Path | str | None = None, level: int = logging.INFO) -> logging.Handler:
    """파일 로그를 붙이고, 콘솔이 있을 때만 화면 출력도 붙인다."""
    global _log_dir
    path = Path(log_path) if log_path is not None else default_log_path()
    handler = setup_file_logging(path)
    _log_dir = path.parent
    if console_logging_wanted():
        logging.basicConfig(level=level, format=FORMAT)
    return handler


def install_excepthooks() -> None:
    """어디서 죽든 로그 파일에 남긴다 — 빌드본에는 오류를 볼 콘솔이 없다."""

    def on_exception(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            return
        log.critical("처리되지 않은 예외로 종료한다", exc_info=(exc_type, exc_value, exc_tb))

    def on_thread_exception(args) -> None:
        if issubclass(args.exc_type, SystemExit):
            return
        log.critical(
            "스레드 %s 에서 처리되지 않은 예외가 발생했다",
            getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = on_exception
    threading.excepthook = on_thread_exception


def show_error_box(title: str, message: str) -> None:
    """시작 자체가 실패하면 콘솔이 없어 알릴 길이 메시지 상자뿐이다. 여기서 또 죽으면 안 된다."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        MB_ICONERROR = 0x10
        ctypes.windll.user32.MessageBoxW(None, message, title, MB_ICONERROR)
    except Exception:
        log.exception("오류 상자를 띄우지 못했다")


def report_fatal(message: str, *, title: str = "루미아 브리핑룸") -> None:
    log.critical("%s", message)
    folder = _log_dir or default_log_path().parent
    show_error_box(title, f"{message}\n\n자세한 내용은 로그를 확인하세요:\n{folder}")
