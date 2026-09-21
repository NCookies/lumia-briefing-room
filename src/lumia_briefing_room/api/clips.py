"""클립 스캔. (plan-ui.md §2.2)

매번 clips_dir 를 훑는다 — 클립 수천 개 수준까지는 캐싱 없이 충분하다(SPEC §7.9).
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

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
    """clips_dir 바로 아래의 메타데이터를 전부 읽는다. 읽는 도중 지워졌거나 깨진 파일은 건너뛴다(동시에 삭제하는 요청과 겹칠 수 있다).

    `glob("*.json")` 은 비재귀라 `.trash`/`.thumbs`/`.proxy` 서브폴더 안의
    파일은 애초에 안 잡힌다 — 동시에 이 함수는 `clips_dir` 자리에 `.trash`
    폴더를 직접 넘겨 휴지통만 스캔하는 용도로도 쓰인다(api/app.py).
    """
    if not clips_dir.exists():
        return []
    clips = []
    for path in sorted(clips_dir.glob("*.json")):
        try:
            clips.append(_load_one(path))
        except (OSError, ValueError):
            continue
    return clips


def find_clip(clips_dir: Path, clip_id: str) -> ClipSummary | None:
    meta_path = clips_dir / f"{clip_id}.json"
    try:
        return _load_one(meta_path)
    except (OSError, ValueError):
        return None


def to_summary_dict(clip: ClipSummary) -> dict:
    """pipeline/retention.py::select_for_auto_clean() 이 요구하는 _created_at/_size_bytes 를 채운다."""
    return {**clip.meta, "_created_at": clip.created_at, "_size_bytes": clip.size_bytes}
