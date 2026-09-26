"""중복 실행 방지. (plan-deploy.md D3)

이름 있는 뮤텍스로 두 번째 실행을 감지하고, 이름 있는 이벤트로 이미 떠 있는 앱에게 UI 를 열라고 알린다.
"""

import ctypes
import logging
import sys
import threading
from collections.abc import Callable
from ctypes import wintypes

from lumia_briefing_room import paths

log = logging.getLogger("lumia_briefing_room.single_instance")

DEFAULT_NAME = "LumiaBriefingRoom.SingleInstance"


def default_name() -> str:
    """프로필이 있으면 그 이름이 붙은 뮤텍스를 써서 기본 앱과 동시에 뜰 수 있다."""
    return f"{paths.app_folder_name()}.SingleInstance"
ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT_MS = 500


def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenEventW.restype = wintypes.HANDLE
    kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    return kernel32


class SingleInstance:
    def __init__(self, name: str | None = None):
        name = name or default_name()
        self._mutex_name = f"Local\\{name}"
        self._event_name = f"Local\\{name}.OpenUI"
        self._mutex = None
        self._event = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._k32 = _kernel32() if sys.platform == "win32" else None

    def acquire(self) -> bool:
        """처음 실행이면 True. 이미 떠 있으면 False."""
        if self._k32 is None:
            return True
        ctypes.set_last_error(0)
        handle = self._k32.CreateMutexW(None, False, self._mutex_name)
        already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
        if not handle:
            log.warning("중복 실행 확인용 뮤텍스를 만들지 못했다 - 확인 없이 계속한다")
            return True
        if already_running:
            self._k32.CloseHandle(handle)
            return False
        self._mutex = handle
        self._event = self._k32.CreateEventW(None, False, False, self._event_name)
        return True

    def listen(self, on_signal: Callable[[], None]) -> None:
        """두 번째 실행이 보낸 신호를 백그라운드에서 기다렸다가 콜백을 부른다."""
        if self._k32 is None or not self._event:
            return

        def loop() -> None:
            while not self._stop.is_set():
                if self._k32.WaitForSingleObject(self._event, WAIT_TIMEOUT_MS) == WAIT_OBJECT_0:
                    try:
                        on_signal()
                    except Exception:
                        log.exception("두 번째 실행 신호 처리 중 예외")

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def signal_existing(self) -> bool:
        if self._k32 is None:
            return False
        handle = self._k32.OpenEventW(EVENT_MODIFY_STATE, False, self._event_name)
        if not handle:
            return False
        try:
            return bool(self._k32.SetEvent(handle))
        finally:
            self._k32.CloseHandle(handle)

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        if self._k32 is None:
            return
        for attr in ("_event", "_mutex"):
            handle = getattr(self, attr)
            if handle:
                self._k32.CloseHandle(handle)
                setattr(self, attr, None)
