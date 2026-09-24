"""전송할 라벨을 로컬에서 모은다. 스팀 클립·다시보기 클립·영상을 지운 뒤에도 남는 라벨 보관소(`.labels/`)를 함께 본다."""

from __future__ import annotations

import json
import logging

from lumia_briefing_room.api.clips import scan_clips
from lumia_briefing_room.config import Config, resolve_paths
from lumia_briefing_room.pipeline.label_archive import archive_dir_for
from lumia_briefing_room.telemetry.payload import build_label, label_digest

log = logging.getLogger("lumia_briefing_room.telemetry.collect")


def collect_labels(cfg: Config, install_id: str) -> list[tuple[str, dict, str]]:
    """(clipKey, 계약 라벨, 내용 지문) 목록. 휴지통에 있는 클립은 빼고, 같은 ID 는 지금 있는 클립이 보관소보다 우선한다."""
    resolved = resolve_paths(cfg.paths)
    found: dict[str, dict] = {}
    for root in (resolved.clips, resolved.vod_clips):
        live_ids: set[str] = set()
        for clip in scan_clips(root):
            live_ids.add(clip.id)
            label = build_label(clip.meta, clip_id=clip.id, install_id=install_id)
            if label:
                found[label["clipKey"]] = label
        archive = archive_dir_for(root)
        if not archive.is_dir():
            continue
        for path in sorted(archive.glob("*.json")):
            if path.stem in live_ids:
                continue
            try:
                meta = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(meta, dict):
                continue
            label = build_label(meta, clip_id=str(meta.get("id") or path.stem), install_id=install_id)
            if label:
                found.setdefault(label["clipKey"], label)
    return [(key, label, label_digest(label)) for key, label in found.items()]
