"""앱이 뜰 때 `clipUid` 가 없는 기존 클립에 한 번 채워 넣는다. (plan-ui.md §0 clipUid)

서버의 클립 수정·삭제와 같은 락 안에서 돌아 라벨 저장 같은 요청과 같은 파일을 동시에 고치지 않는다.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from fastapi import FastAPI

from lumia_briefing_room.config import resolve_paths
from lumia_briefing_room.pipeline.clip_fingerprint import pending_fingerprints, store_fingerprint
from lumia_briefing_room.pipeline.clip_uid import backfill_clip_uids

log = logging.getLogger("lumia_briefing_room.api.clip_uid_startup")


def backfill_clip_uids_locked(app: FastAPI) -> int:
    resolved = resolve_paths(app.state.config.paths)
    filled = 0
    for root in (resolved.library_steam, resolved.library_vod):
        with app.state.lock:
            try:
                filled += backfill_clip_uids(root)
            except Exception:
                log.exception("clipUid 채우기 중 오류: %s", root)
    if filled:
        log.info("기존 클립 %d개에 clipUid 를 채웠다", filled)
    recorded = record_legacy_fingerprints(app)
    if recorded:
        log.info("태그 없는 옛 클립 %d개의 영상 지문을 기록했다", recorded)
    return filled


def record_legacy_fingerprints(app: FastAPI) -> int:
    """태그 없는 옛 클립의 영상 지문을 기록한다. 영상을 읽는 일은 락 밖에서, 기록만 락 안에서 한다."""
    resolved = resolve_paths(app.state.config.paths)
    recorded = 0
    for library in (resolved.library_steam, resolved.library_vod):
        try:
            pending = pending_fingerprints(library, resolved.clip_roots)
        except Exception:
            log.exception("영상 지문 대상 찾기 중 오류: %s", library)
            continue
        for meta_path, video in pending:
            with app.state.lock:
                try:
                    recorded += store_fingerprint(meta_path, video)
                except Exception:
                    log.exception("영상 지문 기록 중 오류: %s", meta_path)
    return recorded


def start_backfill_thread(app: FastAPI, *, on_done: Callable[[], None] | None = None) -> threading.Thread:
    def run() -> None:
        backfill_clip_uids_locked(app)
        if on_done is not None:
            on_done()

    thread = threading.Thread(target=run, daemon=True, name="clip-uid-backfill")
    thread.start()
    return thread
