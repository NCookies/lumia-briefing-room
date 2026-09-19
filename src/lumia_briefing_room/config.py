from __future__ import annotations

import os
import shutil
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BUNDLED_FFMPEG = _PROJECT_ROOT / "vendor" / "ffmpeg" / "ffmpeg.exe"


def discover_ffmpeg() -> Path | None:
    """ffmpeg 실행 파일을 찾는다.

    SPEC §4: ffmpeg 번들이 필수다. 우선순위:
      1) LUMIA_FFMPEG 환경변수
      2) 번들된 위치 (vendor/ffmpeg/ffmpeg.exe)
      3) PATH
    """
    env_path = os.environ.get("LUMIA_FFMPEG")
    if env_path and Path(env_path).exists():
        return Path(env_path)

    if _BUNDLED_FFMPEG.exists():
        return _BUNDLED_FFMPEG

    found = shutil.which("ffmpeg")
    return Path(found) if found else None
