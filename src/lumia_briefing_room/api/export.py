"""클립 내보내기와 서버 쪽 폴더 탐색.

브라우저는 로컬 절대경로를 다룰 수 없어서, 127.0.0.1 에서 도는 이 서버가
폴더 목록을 알려주고 파일을 직접 복사한다.
"""

import os
import re
import shutil
import string
from pathlib import Path

_INVALID_CHARS = re.compile(r'[<>:"/\|?*\x00-\x1f]')


def list_roots() -> list[str]:
    if os.name == "nt":
        return [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    return ["/"]


def list_subdirs(path: Path) -> list[str]:
    names = []
    for child in path.iterdir():
        try:
            if child.is_dir():
                names.append(child.name)
        except OSError:
            continue
    return sorted(names, key=str.casefold)


def parent_of(path: Path) -> str | None:
    parent = path.parent
    return None if parent == path else str(parent)


def sanitize_filename(name: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", name).strip(" .")
    return cleaned or "clip"


def is_valid_folder_name(name: str) -> bool:
    return bool(name.strip()) and name == sanitize_filename(name) and name not in {".", ".."}


def unique_destination(directory: Path, stem: str) -> Path:
    candidate = directory / f"{stem}.mp4"
    n = 2
    while candidate.exists():
        candidate = directory / f"{stem} ({n}).mp4"
        n += 1
    return candidate


def export_video(source: Path, directory: Path, stem: str) -> Path:
    dest = unique_destination(directory, sanitize_filename(stem))
    shutil.copy2(source, dest)
    return dest
