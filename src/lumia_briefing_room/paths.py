"""번들 리소스(본보기·캐릭터표·프론트 dist·ffmpeg)의 위치를 한 곳에서 정한다. (plan-deploy.md D1)

소스 트리에서는 저장소 루트, PyInstaller 빌드본에서는 압축이 풀리는 폴더(`sys._MEIPASS`)나 exe 옆이다.
"""

import logging
import os
import re
import sys
from pathlib import Path

log = logging.getLogger("lumia_briefing_room.paths")

RESOURCE_DIR_ENV = "LUMIA_RESOURCE_DIR"
PROFILE_ENV = "LUMIA_PROFILE"
APP_FOLDER = "LumiaBriefingRoom"
_PROFILE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,20}$")
_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_warned: set[str] = set()


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_dir(*, frozen: bool | None = None, meipass: str | None = None, executable: str | None = None) -> Path:
    override = os.environ.get(RESOURCE_DIR_ENV)
    if override:
        return Path(override)
    if frozen is None:
        frozen = is_frozen()
    if not frozen:
        return _SOURCE_ROOT
    meipass = meipass if meipass is not None else getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(executable or sys.executable).resolve().parent


def profile() -> str:
    """같은 PC 에서 앱을 둘 이상 따로 돌릴 때(개발판·설치판) 쓰는 이름. 비면 기본(분리 없음). 안전한 짧은 이름만 받는다."""
    name = os.environ.get(PROFILE_ENV, "").strip()
    return name if _PROFILE_PATTERN.match(name) else ""


def app_folder_name() -> str:
    """사용자별 폴더 이름(설정·로그·전송 상태·클립 기본 위치). 프로필이 있으면 `LumiaBriefingRoom-<프로필>`."""
    name = profile()
    return f"{APP_FOLDER}-{name}" if name else APP_FOLDER


def data_dir() -> Path:
    return resource_dir() / "data"


def characters_path() -> Path:
    return data_dir() / "characters.json"


def templates_dir(kind: str) -> Path:
    return data_dir() / "templates" / kind


def frontend_dist_dir() -> Path:
    return resource_dir() / "frontend" / "dist"


def bundled_ffmpeg_dir() -> Path:
    return resource_dir() / "vendor" / "ffmpeg"


def warn_missing(what: str, path: Path) -> None:
    """번들 파일이 없으면 조용히 넘어가지 않고 한 번 경고한다(본보기가 없으면 판독이 조용히 꺼진다)."""
    key = f"{what}:{path}"
    if key in _warned:
        return
    _warned.add(key)
    log.warning("%s 파일을 찾을 수 없다: %s (해당 판독이 꺼진다)", what, path)
