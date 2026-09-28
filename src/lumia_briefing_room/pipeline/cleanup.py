"""자동 정리 실행기. (SPEC §7.6)

retention.py 로 한도(나이·개수·용량)를 넘은 클립을 고르고, delete_helper.py 로
바로 지운다(휴지통으로 보내거나 영구 삭제) — 예전처럼 앱 자체 휴지통에 옮겨
두었다가 유예 기간 뒤에 지우는 중간 단계는 없다.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lumia_briefing_room.api.clips import scan_clips, to_summary_dict
from lumia_briefing_room.config import RetentionConfig, load_config, resolve_paths
from lumia_briefing_room.pipeline.clip_assets import resolve_result_image
from lumia_briefing_room.pipeline.delete_helper import delete_clip
from lumia_briefing_room.pipeline.game_records import clear_records, record_game, records_dir_for
from lumia_briefing_room.pipeline.label_archive import archive_dir_for, archive_if_labeled
from lumia_briefing_room.pipeline.proxy import remove_orphan_proxies
from lumia_briefing_room.pipeline.retention import select_for_auto_clean

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 3600.0


@dataclass(frozen=True)
class CleanupPlan:
    to_delete: list[Path]
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


def plan_cleanup(clips_dir: Path, cfg: RetentionConfig, *, now: datetime | None = None) -> CleanupPlan:
    now = now or datetime.now(timezone.utc)
    if not cfg.auto_clean_enabled:
        return CleanupPlan([], 0)

    entries = []
    for clip in scan_clips(clips_dir):
        entry = to_summary_dict(clip)
        entry["_created_at"] = _game_time(clip.meta, clip.created_at)
        entry["_path"] = clip.meta_path
        entries.append(entry)

    selected = select_for_auto_clean(entries, cfg, now=lambda: now)
    to_delete = [e["_path"] for e in selected]
    freed = sum(e["_size_bytes"] for e in selected)
    return CleanupPlan(to_delete, freed)


def remove_orphan_result_images(clips_dir: Path) -> list[Path]:
    referenced: set[Path] = set()
    for clip in scan_clips(clips_dir):
        image = resolve_result_image(clip.meta_path, clip.meta)
        if image is not None:
            referenced.add(image.resolve())

    thumbs = clips_dir / ".thumbs"
    removed: list[Path] = []
    if thumbs.exists():
        for image in thumbs.glob("*_result.jpg"):
            if image.resolve() not in referenced:
                image.unlink(missing_ok=True)
                removed.append(image)
    return removed


def run_cleanup(clips_dir: Path, cfg: RetentionConfig, *, now: datetime | None = None) -> CleanupPlan:
    now = now or datetime.now(timezone.utc)
    plan = plan_cleanup(clips_dir, cfg, now=now)
    records_dir = records_dir_for(clips_dir)
    if not cfg.keep_game_records:
        clear_records(records_dir)
        records_dir = None
    if not cfg.auto_clean_enabled:
        return plan

    archive_dir = archive_dir_for(clips_dir)
    for meta_path in plan.to_delete:
        delete_clip(meta_path, mode=cfg.delete_mode, archive_dir=archive_dir, records_dir=records_dir)
    remove_orphan_result_images(clips_dir)
    remove_orphan_proxies(clips_dir)
    return plan


def make_cleanup_runner(config_path: Path | None) -> Callable[[], CleanupPlan]:
    """설정 파일을 실행 때마다 다시 읽는다 — 사용자가 옵션에서 바꾼 값이 재시작 없이 반영된다."""

    def run() -> CleanupPlan:
        cfg = load_config(config_path)
        resolved = resolve_paths(cfg.paths)
        return run_cleanup(resolved.clips, cfg.retention)

    return run


def cleanup_loop(run: Callable[[], object], stop: threading.Event, *, interval_sec: float = DEFAULT_INTERVAL_SEC) -> None:
    while not stop.is_set():
        try:
            run()
        except Exception:
            log.exception("자동 정리 실패 - 다음 주기에 다시 시도한다")
        if stop.wait(interval_sec):
            break
