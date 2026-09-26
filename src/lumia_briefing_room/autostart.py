"""Windows 레지스트리 Run 키를 이용한 자동 시작. (SPEC §7.7 ui.autoStart)

HKEY_CURRENT_USER 아래라 관리자 권한이 필요 없다.
"""

import sys

from lumia_briefing_room import paths

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


def build_command(*, frozen: bool, executable: str) -> str:
    """빌드본에서 sys.executable 은 앱 exe 라 `-m` 인자가 의미 없다."""
    if frozen:
        return f'"{executable}"'
    return f'"{executable}" -m lumia_briefing_room.cli.app'


def current_command() -> str:
    """레지스트리에 등록할 명령. 앱이 시작할 때마다 덮어쓰므로 개발 PC 에 남은 옛 명령도 바뀐다."""
    return build_command(frozen=paths.is_frozen(), executable=sys.executable)


def apply_setting(cfg, *, app_name: str | None = None) -> None:
    """SPEC §7.7 `ui.autoStart` 를 실제 레지스트리 상태에 반영한다."""
    if not is_supported() or paths.profile():
        return
    name = app_name or APP_NAME
    if cfg.ui.auto_start:
        enable(current_command(), app_name=name)
    else:
        disable(app_name=name)
