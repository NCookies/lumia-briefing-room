"""클립 삭제 도우미: Windows 휴지통 이동 또는 영구 삭제. (docs/plan-ui.md §0)

앱 자체 휴지통(유예 기간·복구 버튼)을 없애는 대신, 삭제 시점에 (1) 라벨이 있으면
라벨 보관소에 근거를 남기고 (2) 게임 기록을 남긴 뒤 (3) 실제 파일을 Windows
휴지통으로 보내거나 영구 삭제한다. 이 세 단계는 수동 삭제·자동 정리·다시 분석·
구간 분할·다시보기 영상 삭제가 모두 공유한다.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from pathlib import Path

from send2trash import send2trash as _send2trash

from lumia_briefing_room.pipeline.cleanup_registry import registry as cleanup_preview_registry
from lumia_briefing_room.pipeline.clip_assets import resolve_thumbnail
from lumia_briefing_room.pipeline.game_records import record_game
from lumia_briefing_room.pipeline.label_archive import archive_if_labeled

RECYCLE = "recycle"
PERMANENT = "permanent"


def clip_files(meta_path: Path, meta: dict, *, proxy: Path | None = None) -> list[Path]:
    """클립 하나에 딸린, 실제로 존재하는 파일 전부(메타데이터·mp4·썸네일·재생용 프록시)."""
    files = [meta_path, meta_path.with_suffix(".mp4")]
    thumb = resolve_thumbnail(meta_path, meta)
    if thumb is not None:
        files.append(thumb)
    if proxy is not None:
        files.append(proxy)
    return [f for f in files if f.exists()]


def send_to_recycle_bin(paths: Iterable[Path]) -> None:
    for path in paths:
        _send2trash(str(path))


def _unlink_with_retry(path: Path, *, attempts: int = 5) -> None:
    """Windows 는 다른 요청이 그 파일을 읽는 중이면 지우기가 PermissionError 로 실패한다 — 잠깐 기다려 다시 시도한다."""
    for attempt in range(attempts):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05)


def permanently_delete(paths: Iterable[Path]) -> None:
    for path in paths:
        _unlink_with_retry(path)


def delete_clip(
    meta_path: Path,
    *,
    mode: str,
    archive_dir: Path | None = None,
    records_dir: Path | None = None,
    proxy: Path | None = None,
) -> None:
    """클립 하나를 지운다: 라벨 보관 → 게임 기록 → 실제 파일 삭제(휴지통 또는 영구) 순서.

    라벨·게임 기록은 파일을 지우기 전에 남겨야 하므로(둘 다 메타데이터를 다시 읽는다) 순서가 중요하다.
    """
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    archive_if_labeled(meta_path, archive_dir)
    record_game(meta_path, records_dir)
    files = clip_files(meta_path, meta, proxy=proxy)
    if mode == PERMANENT:
        permanently_delete(files)
    else:
        send_to_recycle_bin(files)
    cleanup_preview_registry.notify_clips_changed()
