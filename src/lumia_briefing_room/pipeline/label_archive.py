"""영상을 지워도 남기는 라벨 보관소. 라벨이 붙은 클립만, 근거·라벨 메타데이터(수 KB)만 `clips/.labels/` 에 둔다.

가중치·검출기 평가는 영상이 아니라 메타데이터만 읽으므로, 용량 때문에 영상을 정리해도 라벨링 노력이 쌓이게 한다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from lumia_briefing_room.pipeline.clip_uid import UID_KEY, new_clip_uid

LABELS = ("pvp", "pve")
ARCHIVE_DIRNAME = ".labels"


def archive_dir_for(clips_dir: Path) -> Path:
    return clips_dir / ARCHIVE_DIRNAME


def archive_if_labeled(meta_path: Path, archive_dir: Path | None) -> Path | None:
    if archive_dir is None or not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("userLabel") not in LABELS:
        return None
    kept = {k: v for k, v in meta.items() if k not in ("thumbnailPath", "deletedAt")}
    if isinstance(kept.get("matchResult"), dict):
        kept["matchResult"] = {k: v for k, v in kept["matchResult"].items() if k != "imagePath"}
    kept["id"] = meta_path.stem
    if not kept.get(UID_KEY):
        kept[UID_KEY] = new_clip_uid()
    kept["archivedAt"] = datetime.now(timezone.utc).isoformat()
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / f"{meta_path.stem}.json"
    target.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_archived(clips_dir: Path) -> list[dict]:
    archive = archive_dir_for(clips_dir)
    if not archive.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(archive.glob("*.json"))]
