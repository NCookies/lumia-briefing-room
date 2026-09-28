"""다시보기 영상의 방송·게임 날짜 계산. (plan-vod.md V8)

우선순위: 사용자가 고친 값 > 파일 메타데이터(ffprobe format_tags.creation_time) > 파일 수정 시각.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def date_from_creation_time(creation_time: str | None) -> str | None:
    """ffprobe format_tags.creation_time(보통 'YYYY-MM-DDTHH:MM:SS.ffffffZ')에서 로컬 날짜를 뽑는다."""
    if not creation_time:
        return None
    text = creation_time.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().date().isoformat()


def date_from_mtime(mtime: float) -> str:
    return datetime.fromtimestamp(mtime).date().isoformat()


def resolve_video_date(*, override: str | None, creation_time: str | None, mtime: float | None) -> str | None:
    if override and override.strip():
        return override.strip()
    from_meta = date_from_creation_time(creation_time)
    if from_meta:
        return from_meta
    if mtime is not None:
        return date_from_mtime(mtime)
    return None


def is_valid_iso_date(text: str) -> bool:
    if not _ISO_DATE.match(text or ""):
        return False
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return False
    return True
