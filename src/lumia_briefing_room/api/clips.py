"""클립 스캔. (plan-ui.md §2.2)

매번 clips_dir 를 훑는다 — 클립 수천 개 수준까지는 캐싱 없이 충분하다(SPEC §7.9).
"""

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from collections.abc import Iterable
from pathlib import Path

from lumia_briefing_room.pipeline.clip_files import find_video, link_all

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


def _summary(meta_path: Path, meta: dict, video: Path | None) -> ClipSummary:
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

    영상은 `link_all` 이 잇는다: 영상 안 `clipUid` 태그 → 파일 이름 → 기록된 지문 순(정보는 library, 영상은 저장 폴더 어디든).
    같은 ID 태그의 복사본은 `<ID>~<해시>` 로 따로 나온다. `glob("*.json")` 은 비재귀라 `.thumbs`/`.proxy` 서브폴더 안의 파일은 안 잡힌다.
    """
    if not meta_dir.exists():
        return []
    loaded: list[tuple[Path, dict]] = []
    for path in sorted(meta_dir.glob("*.json")):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
            path.stat()
        except (OSError, ValueError):
            continue
        if isinstance(meta, dict):
            loaded.append((path, meta))
    links = link_all([(meta_dir, [(p.stem, m) for p, m in loaded])], video_roots)
    clips: list[ClipSummary] = []
    by_id = {p.stem: (p, m) for p, m in loaded}
    for path, meta in loaded:
        try:
            clips.append(_summary(path, meta, links.primary.get((meta_dir, path.stem))))
        except OSError:
            continue
    for _, extra_id, base_id, video in links.extras:
        path, meta = by_id[base_id]
        try:
            clips.append(replace(_summary(path, meta, video), id=extra_id))
        except OSError:
            continue
    return clips


def find_clip(meta_dir: Path, clip_id: str, video_roots: Iterable[Path] = ()) -> ClipSummary | None:
    base_id = clip_id.partition("~")[0]
    meta_path = meta_dir / f"{base_id}.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            return None
        video = find_video(meta_dir, clip_id, video_roots, meta)
        if video is None and "~" in clip_id:
            return None
        clip = _summary(meta_path, meta, video)
    except (OSError, ValueError):
        return None
    return replace(clip, id=clip_id)


def find_clips(meta_dir: Path, clip_ids: Iterable[str], video_roots: Iterable[Path] = ()) -> dict[str, ClipSummary]:
    """`find_clip` 을 여러 ID 에 한 번에: 영상 잇기(`link_all`, 영상 폴더 전체를 훑는다)를 ID 마다 되풀이하지 않고 한 번만 한다. 못 찾은 ID 는 빠진다."""
    metas: dict[str, tuple[Path, dict]] = {}
    for clip_id in dict.fromkeys(clip_ids):
        base_id = clip_id.partition("~")[0]
        if base_id in metas:
            continue
        meta_path = meta_dir / f"{base_id}.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(meta, dict):
            metas[base_id] = (meta_path, meta)
    if not metas:
        return {}
    links = link_all([(meta_dir, [(base, meta) for base, (_, meta) in metas.items()])], tuple(video_roots))
    extras = {extra_id: video for _, extra_id, _, video in links.extras}
    found: dict[str, ClipSummary] = {}
    for clip_id in dict.fromkeys(clip_ids):
        base_id = clip_id.partition("~")[0]
        if base_id not in metas:
            continue
        meta_path, meta = metas[base_id]
        video = extras.get(clip_id) if "~" in clip_id else links.primary.get((meta_dir, base_id))
        if video is None and "~" in clip_id:
            continue
        try:
            found[clip_id] = replace(_summary(meta_path, meta, video), id=clip_id)
        except OSError:
            continue
    return found


def to_summary_dict(clip: ClipSummary) -> dict:
    """pipeline/retention.py::select_for_auto_clean() 이 요구하는 _created_at/_size_bytes 를 채운다."""
    return {**clip.meta, "_created_at": clip.created_at, "_size_bytes": clip.size_bytes}
