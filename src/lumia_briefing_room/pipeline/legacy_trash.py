"""옛 버전(앱 자체 휴지통이 있던 시절)의 `clips/.trash` 폴더를 한 번 정리한다. (docs/plan-ui.md §0-(7))

앱 휴지통 기능 자체는 없어졌지만, 업그레이드 전에 이미 삭제해 둔 클립이 사용자 PC 에
남아 있을 수 있다. 첫 실행에 남은 클립이 있으면 "클립 목록으로 복구" 또는
"Windows 휴지통으로 보내기" 중 하나를 고르게 한다. 폴더가 비면 더 묻지 않는다
(그래서 서버에 상태를 남기지 않는다 — 남은 클립 유무 자체가 상태다).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from lumia_briefing_room.api.clips import scan_clips
from lumia_briefing_room.pipeline.clip_assets import resolve_thumbnail
from lumia_briefing_room.pipeline.delete_helper import delete_clip
from lumia_briefing_room.pipeline.label_archive import archive_dir_for

LEGACY_TRASH_DIRNAME = ".trash"


def legacy_trash_dir(root: Path) -> Path:
    return root / LEGACY_TRASH_DIRNAME


def count_legacy_trash(*roots: Path) -> int:
    total = 0
    for root in roots:
        trash = legacy_trash_dir(root)
        if trash.exists():
            total += len(list(trash.glob("*.json")))
    return total


def _restore_one(meta_path: Path, clips_dir: Path) -> None:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    trash_dir = meta_path.parent
    files = [meta_path.with_suffix(".mp4")]
    thumb = resolve_thumbnail(meta_path, meta)
    if thumb is not None:
        files.append(thumb)
    files.append(meta_path)

    moved_meta_path = clips_dir / meta_path.name
    for f in files:
        try:
            rel = f.relative_to(trash_dir)
        except ValueError:
            rel = Path(f.name)
        dest = clips_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(dest))

    fresh = json.loads(moved_meta_path.read_text(encoding="utf-8"))
    fresh.pop("deletedAt", None)
    moved_meta_path.write_text(json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8")


def restore_legacy_trash(root: Path) -> int:
    """옛 휴지통의 클립을 전부 원래 클립 목록으로 되돌린다."""
    clips = scan_clips(legacy_trash_dir(root))
    for clip in clips:
        _restore_one(clip.meta_path, root)
    return len(clips)


def recycle_legacy_trash(root: Path) -> int:
    """옛 휴지통의 클립을 전부 Windows 휴지통으로 보낸다(라벨은 보관소에 남긴다)."""
    clips = scan_clips(legacy_trash_dir(root))
    for clip in clips:
        delete_clip(clip.meta_path, mode="recycle", archive_dir=archive_dir_for(root))
    return len(clips)
