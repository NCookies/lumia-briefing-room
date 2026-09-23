import logging
import subprocess
import sys
import threading
from pathlib import Path

from lumia_briefing_room import startup


def test_console_logging_is_skipped_when_there_is_no_stderr():
    assert startup.console_logging_wanted(stderr=None) is False
    assert startup.console_logging_wanted(stderr=sys.stderr) is True


def test_a_detached_stderr_without_fileno_is_still_usable():
    class Fake:
        def write(self, text):
            return len(text)

    assert startup.console_logging_wanted(stderr=Fake()) is True


def test_setup_logging_without_console_still_writes_to_the_file(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)
    root_handlers = list(logging.getLogger().handlers)
    handler = startup.setup_logging(log_path=tmp_path / "logs" / "app.log")
    try:
        logging.getLogger("lumia_briefing_room.test").error("파일로 남아야 한다")
    finally:
        logging.getLogger("lumia_briefing_room").removeHandler(handler)
        handler.close()

    assert logging.getLogger().handlers == root_handlers
    assert "파일로 남아야 한다" in (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")


def test_excepthooks_write_the_traceback_to_the_log(tmp_path: Path):
    log_path = tmp_path / "app.log"
    handler = startup.setup_logging(log_path=log_path)
    previous = (sys.excepthook, threading.excepthook)
    try:
        startup.install_excepthooks()
        try:
            raise ValueError("메인 스레드 폭발")
        except ValueError:
            sys.excepthook(*sys.exc_info())

        thread = threading.Thread(target=lambda: (_ for _ in ()).throw(RuntimeError("스레드 폭발")))
        thread.start()
        thread.join()
    finally:
        sys.excepthook, threading.excepthook = previous
        logging.getLogger("lumia_briefing_room").removeHandler(handler)
        handler.close()

    text = log_path.read_text(encoding="utf-8")
    assert "메인 스레드 폭발" in text and "ValueError" in text
    assert "스레드 폭발" in text and "RuntimeError" in text


def test_keyboard_interrupt_is_not_reported_as_a_crash(tmp_path: Path):
    log_path = tmp_path / "app.log"
    handler = startup.setup_logging(log_path=log_path)
    previous = sys.excepthook
    try:
        startup.install_excepthooks()
        sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    finally:
        sys.excepthook = previous
        logging.getLogger("lumia_briefing_room").removeHandler(handler)
        handler.close()

    assert "KeyboardInterrupt" not in log_path.read_text(encoding="utf-8")


def test_show_error_box_never_raises_even_without_a_window_station(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    startup.show_error_box("제목", "본문")


def test_fatal_error_is_logged_and_shown(tmp_path: Path, monkeypatch):
    shown = []
    monkeypatch.setattr(startup, "show_error_box", lambda title, message: shown.append((title, message)))
    log_path = tmp_path / "app.log"
    handler = startup.setup_logging(log_path=log_path)
    try:
        startup.report_fatal("포트를 열지 못했다")
    finally:
        logging.getLogger("lumia_briefing_room").removeHandler(handler)
        handler.close()

    assert shown and "포트를 열지 못했다" in shown[0][1]
    assert str(log_path.parent) in shown[0][1]
    assert "포트를 열지 못했다" in log_path.read_text(encoding="utf-8")


def test_real_process_without_stderr_logs_to_file_and_survives(tmp_path: Path):
    """콘솔에서 분리한 pythonw.exe 는 sys.stderr 가 None 이다 — --noconsole 빌드와 같은 상황이다."""
    import os

    import pytest

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if sys.platform != "win32" or not pythonw.exists():
        pytest.skip("Windows 의 pythonw.exe 가 필요하다")

    log_path = tmp_path / "noconsole.log"
    done = tmp_path / "done.txt"
    script = tmp_path / "run.py"
    script.write_text(
        "import sys, threading, pathlib\n"
        "from lumia_briefing_room import startup\n"
        "assert sys.stderr is None and sys.stdout is None\n"
        f"startup.setup_logging(log_path=r'{log_path}')\n"
        "startup.install_excepthooks()\n"
        "t = threading.Thread(target=lambda: 1 / 0)\n"
        "t.start(); t.join()\n"
        f"pathlib.Path(r'{done}').write_text('ok', encoding='utf-8')\n",
        encoding="utf-8",
    )

    DETACHED_PROCESS = 0x00000008
    proc = subprocess.Popen(
        [str(pythonw), str(script)],
        creationflags=DETACHED_PROCESS,
        close_fds=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert proc.wait(timeout=60) == 0

    assert done.read_text(encoding="utf-8") == "ok"
    assert "ZeroDivisionError" in log_path.read_text(encoding="utf-8")
