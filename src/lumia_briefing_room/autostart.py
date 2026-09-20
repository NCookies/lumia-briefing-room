"""Windows 레지스트리 Run 키를 이용한 자동 시작. (SPEC §7.7 ui.autoStart)

HKEY_CURRENT_USER 아래라 관리자 권한이 필요 없다.
"""

import sys

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "LumiaBriefingRoom"


def is_supported() -> bool:
    return sys.platform == "win32"


def _open_key(write: bool):
    import winreg

    access = winreg.KEY_WRITE if write else winreg.KEY_READ
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, access)


def is_enabled(*, app_name: str = APP_NAME) -> bool:
    return get_command(app_name=app_name) is not None


def get_command(*, app_name: str = APP_NAME) -> str | None:
    import winreg

    try:
        with _open_key(write=False) as key:
            value, _ = winreg.QueryValueEx(key, app_name)
            return value
    except FileNotFoundError:
        return None


def enable(command: str, *, app_name: str = APP_NAME) -> None:
    import winreg

    with _open_key(write=True) as key:
        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, command)


def disable(*, app_name: str = APP_NAME) -> None:
    import winreg

    try:
        with _open_key(write=True) as key:
            winreg.DeleteValue(key, app_name)
    except FileNotFoundError:
        pass
