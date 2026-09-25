"""저장소 루트의 `.env`(gitignore)를 읽어 환경변수로 채운다. 이미 있는 환경변수는 덮어쓰지 않는다.

서버 주소·토큰은 공개 저장소에 없으므로 빌드(`build_release.py`)와 라벨 수집(`pull_labels.py`)이 여기서 받는다.
형식은 한 줄에 `KEY=VALUE`, `#` 로 시작하는 줄은 주석이고 값 뒤 ` # …` 도 주석이다(따옴표 안의 `#` 은 값).
"""

from __future__ import annotations

import os
from pathlib import Path


def _clean_value(raw: str) -> str:
    """따옴표로 감싼 값은 그 안을 그대로, 아니면 ` #` 뒤(줄 끝 주석)를 잘라낸다."""
    raw = raw.strip()
    if raw[:1] in ("\"", "'"):
        end = raw.find(raw[0], 1)
        if end != -1:
            return raw[1:end]
        return raw.strip("\"'")
    for i, ch in enumerate(raw):
        if ch == "#" and i > 0 and raw[i - 1].isspace():
            return raw[:i].strip()
    return raw


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
        key, value = key.strip(), _clean_value(value)
        if key and key not in environ:
            environ[key] = value
            loaded.append(key)
    return loaded


def normalize_server_url(url: str) -> str:
    """서버 주소에 `http(s)://` 가 없으면 `https://` 를 붙이고 끝의 `/` 를 뗀다(호스트 이름만 적어도 동작하게)."""
    url = url.strip().rstrip("/")
    if url and "://" not in url:
        url = "https://" + url
    return url
