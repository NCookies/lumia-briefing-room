"""자동 정리 실행기. (SPEC §7.6)

retention.py 의 선택/이동 함수들을 실제로 돌린다: 한도(나이·개수·용량)를 넘은 클립은 휴지통으로(또는 즉시 삭제),
휴지통에서 유예 기간이 지난 것은 영구 삭제, 클립이 다 사라진 경기의 결과표 이미지는 함께 정리한다.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lumia_briefing_room.api.clips import scan_clips, to_summary_dict
from lumia_briefing_room.config import RetentionConfig, load_config, resolve_paths
from lumia_briefing_room.pipeline.game_records import clear_records, record_game, records_dir_for
from lumia_briefing_room.pipeline.label_archive import archive_dir_for, archive_if_labeled
from lumia_briefing_room.pipeline.retention import (
    _clip_files,
    list_expired,
    purge_expired,
    select_for_auto_clean,
    trash_clip,
)

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 3600.0


@dataclass(frozen=True)
class CleanupPlan:
    to_trash: list[Path]
    to_purge: list[Path]
    bytes_to_free: int


def _game_time(meta: dict, fallback: datetime) -> datetime:
    """나이는 경기 시각 기준이다. 메타데이터 파일 수정 시각은 라벨을 찍을 때마다 바뀐다."""
    start = meta.get("matchStartUtc")
    if start:
        try:
            return datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            pass
    return fallback


def _size(meta_path: Path) -> int:
    mp4 = meta_path.with_suffix(".mp4")
    return mp4.stat().st_size if mp4.exists() else 0


def plan_cleanup(
    clips_dir: Path, trash_dir: Path, cfg: RetentionConfig, *, now: datetime | None = None
) -> CleanupPlan:
    now = now or datetime.now(timezone.utc)
    if not cfg.auto_clean_enabled:
        return CleanupPlan([], [], 0)

    entries = []
    for clip in scan_clips(clips_dir):
        entry = to_summary_dict(clip)
        entry["_created_at"] = _game_time(clip.meta, clip.created_at)
        entry["_path"] = clip.meta_path
        entries.append(entry)

    selected = select_for_auto_clean(entries, cfg, now=lambda: now)
    to_trash = [e["_path"] for e in selected]
    to_purge = list_expired(trash_dir, trash_days=cfg.trash_days, now=lambda: now)
    freed = sum(e["_size_bytes"] for e in selected) + sum(_size(p) for p in to_purge)
    return CleanupPlan(to_trash, to_purge, freed)


def _delete_clip_permanently(
    meta_path: Path, archive_dir: Path | None = None, records_dir: Path | None = None
) -> None:
    archive_if_labeled(meta_path, archive_dir)
    record_game(meta_path, records_dir)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for f in _clip_files(meta_path, meta):
        f.unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)


def remove_orphan_result_images(clips_dir: Path, trash_dir: Path) -> list[Path]:
    referenced: set[Path] = set()
    for root in (clips_dir, trash_dir):
        for clip in scan_clips(root):
            image = (clip.meta.get("matchResult") or {}).get("imagePath")
            if image:
                referenced.add(Path(image).resolve())

    thumbs = clips_dir / ".thumbs"
    removed: list[Path] = []
    if thumbs.exists():
        for image in thumbs.glob("*_result.jpg"):
            if image.resolve() not in referenced:
                image.unlink(missing_ok=True)
                removed.append(image)
    return removed


def run_cleanup(
    clips_dir: Path, trash_dir: Path, cfg: RetentionConfig, *, now: datetime | None = None
) -> CleanupPlan:
    now = now or datetime.now(timezone.utc)
    plan = plan_cleanup(clips_dir, trash_dir, cfg, now=now)
    records_dir = records_dir_for(clips_dir)
    if not cfg.keep_game_records:
        clear_records(records_dir)
        records_dir = None
    if not cfg.auto_clean_enabled:
        return plan

    for meta_path in plan.to_trash:
        if cfg.delete_mode == "permanent":
            _delete_clip_permanently(meta_path, archive_dir_for(clips_dir), records_dir)
        else:
            trash_clip(meta_path, trash_dir, now=lambda: now)
    purge_expired(
        trash_dir,
        trash_days=cfg.trash_days,
        now=lambda: now,
        archive_dir=archive_dir_for(clips_dir),
        records_dir=records_dir,
    )
    remove_orphan_result_images(clips_dir, trash_dir)
    return plan


def make_cleanup_runner(config_path: Path | None) -> Callable[[], CleanupPlan]:
    """설정 파일을 실행 때마다 다시 읽는다 — 사용자가 옵션에서 바꾼 값이 재시작 없이 반영된다."""

    def run() -> CleanupPlan:
        cfg = load_config(config_path)
        resolved = resolve_paths(cfg.paths)
        return run_cleanup(resolved.clips, resolved.trash, cfg.retention)

    return run


def cleanup_loop(run: Callable[[], object], stop: threading.Event, *, interval_sec: float = DEFAULT_INTERVAL_SEC) -> None:
    while not stop.is_set():
        try:
            run()
        except Exception:
            log.exception("자동 정리 실패 - 다음 주기에 다시 시도한다")
        if stop.wait(interval_sec):
            break
