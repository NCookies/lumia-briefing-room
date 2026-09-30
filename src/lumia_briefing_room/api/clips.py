"""클립 스캔. (plan-ui.md §2.2)

매번 clips_dir 를 훑는다 — 클립 수천 개 수준까지는 캐싱 없이 충분하다(SPEC §7.9).
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Iterable
from pathlib import Path

from lumia_briefing_room.pipeline.clip_files import find_video, index_videos

@dataclass(frozen=True)
class ClipSummary:
    id: str
    meta_path: Path
    meta: dict
    size_bytes: int
    created_at: datetime
    video_path: Path | None = None

    @property
    def video(self) -> Path:
        """클립 영상 경로. 못 찾았으면 정보 파일 옆 자리(없는 파일)."""
        return self.video_path or self.meta_path.with_suffix(".mp4")


def _load_one(meta_path: Path, video: Path | None = None) -> ClipSummary:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    mp4_path = video or meta_path.with_suffix(".mp4")
    try:
        size = mp4_path.stat().st_size
    except OSError:
        size = 0
    created_at = datetime.fromtimestamp(meta_path.stat().st_mtime, tz=timezone.utc)
    return ClipSummary(
        id=meta_path.stem, meta_path=meta_path, meta=meta, size_bytes=size, created_at=created_at, video_path=mp4_path
    )


def scan_clips(meta_dir: Path, video_roots: Iterable[Path] = ()) -> list[ClipSummary]:
    """meta_dir 바로 아래의 메타데이터를 전부 읽는다. 읽는 도중 지워졌거나 깨진 파일은 건너뛴다(동시에 삭제하는 요청과 겹칠 수 있다).

    영상은 정보 파일 옆에서, 없으면 `video_roots` 아래에서 파일 이름으로 찾는다(정보는 library, 영상은 저장 폴더).
    `glob("*.json")` 은 비재귀라 `.thumbs`/`.proxy` 서브폴더 안의 파일은 애초에 안 잡힌다.
    """
    if not meta_dir.exists():
        return []
    roots = tuple(video_roots)
    videos = index_videos(meta_dir, roots) if roots else {}
    clips = []
    for path in sorted(meta_dir.glob("*.json")):
        try:
            clips.append(_load_one(path, videos.get(path.stem)))
        except (OSError, ValueError):
            continue
    return clips


def find_clip(meta_dir: Path, clip_id: str, video_roots: Iterable[Path] = ()) -> ClipSummary | None:
    meta_path = meta_dir / f"{clip_id}.json"
    try:
        return _load_one(meta_path, find_video(meta_dir, clip_id, video_roots))
    except (OSError, ValueError):
        return None


def to_summary_dict(clip: ClipSummary) -> dict:
    """pipeline/retention.py::select_for_auto_clean() 이 요구하는 _created_at/_size_bytes 를 채운다."""
    return {**clip.meta, "_created_at": clip.created_at, "_size_bytes": clip.size_bytes}
