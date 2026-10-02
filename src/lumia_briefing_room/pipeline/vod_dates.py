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


def make_vod_day_lookup(cfg):
    """영상 id -> 화면에 보이는 영상 날짜. 목록(`api/vods.py::entry_for`)과 같은 우선순위로 구한다."""
    from pathlib import Path

    from lumia_briefing_room.config import resolve_paths
    from lumia_briefing_room.pipeline.vod_store import load_index

    base = resolve_paths(cfg.paths).library_vod

    def day_of(vod_id: str) -> str | None:
        index = load_index(base, vod_id) if vod_id else None
        mtime = None
        if index and index.get("path"):
            try:
                mtime = Path(index["path"]).stat().st_mtime
            except OSError:
                mtime = None
        return resolve_video_date(
            override=cfg.vod.video_dates.get(vod_id),
            creation_time=(index or {}).get("creationTime"),
            mtime=mtime,
        )

    return day_of
