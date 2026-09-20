"""클립 스캔. (plan-ui.md §2.2)

매번 clips_dir 를 훑는다 — 클립 수천 개 수준까지는 캐싱 없이 충분하다(SPEC §7.9).
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_SKIP_DIRS = {".trash", ".thumbs", ".proxy"}


@dataclass(frozen=True)
class ClipSummary:
    id: str
    meta_path: Path
    meta: dict
    size_bytes: int
    created_at: datetime


def _load_one(meta_path: Path) -> ClipSummary:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    mp4_path = meta_path.with_suffix(".mp4")
    size = mp4_path.stat().st_size if mp4_path.exists() else 0
    created_at = datetime.fromtimestamp(meta_path.stat().st_mtime, tz=timezone.utc)
    return ClipSummary(id=meta_path.stem, meta_path=meta_path, meta=meta, size_bytes=size, created_at=created_at)


def scan_clips(clips_dir: Path) -> list[ClipSummary]:
    """clips_dir 바로 아래(휴지통/썸네일/프록시 폴더 제외)의 메타데이터를 전부 읽는다."""
    if not clips_dir.exists():
        return []
    return [
        _load_one(p)
        for p in sorted(clips_dir.glob("*.json"))
        if p.parent.name not in _SKIP_DIRS
    ]


def find_clip(clips_dir: Path, clip_id: str) -> ClipSummary | None:
    meta_path = clips_dir / f"{clip_id}.json"
    if not meta_path.exists():
        return None
    return _load_one(meta_path)


def to_summary_dict(clip: ClipSummary) -> dict:
    """pipeline/retention.py::select_for_auto_clean() 이 요구하는 _created_at/_size_bytes 를 채운다."""
    return {**clip.meta, "_created_at": clip.created_at, "_size_bytes": clip.size_bytes}
