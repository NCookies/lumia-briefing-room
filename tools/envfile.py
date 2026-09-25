"""저장소 루트의 `.env`(gitignore)를 읽어 환경변수로 채운다. 이미 있는 환경변수는 덮어쓰지 않는다.

서버 주소·토큰은 공개 저장소에 없으므로 빌드(`build_release.py`)와 라벨 수집(`pull_labels.py`)이 여기서 받는다.
형식은 한 줄에 `KEY=VALUE`, `#` 로 시작하는 줄은 주석이다.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path, environ=None) -> list[str]:
    environ = os.environ if environ is None else environ
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    loaded = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("\"'")
        if key and key not in environ:
            environ[key] = value
            loaded.append(key)
    return loaded
