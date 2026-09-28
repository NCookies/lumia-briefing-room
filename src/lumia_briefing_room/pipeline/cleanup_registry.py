"""자동 정리 삭제 예정 미리보기 캐시. (plan-ui.md §0 "자동 정리 삭제 예정 표시")

클립을 만들고 지우고 고치는 코드가 여러 곳이라 각 지점에서 재계산을 직접 부르지
않고, notify_clips_changed() 하나만 부르게 한다. 짧은 시간 안에 여러 번 불려도
디바운스(기본 1.5초)로 마지막 한 번만 cleanup_preview() 를 다시 계산해 메모리에
저장한다 — 파일에는 쓰지 않는다. 화면은 snapshot() 으로 그 결과만 읽는다.

cleanup.py 를 지연 임포트하는 이유: delete_helper.py 등 여러 pipeline 모듈이 이
레지스트리를 모듈 최상단에서 import 하는데, cleanup.py 는 그 모듈들을 거꾸로
import 하므로 최상단에서 서로 붙이면 순환 임포트가 된다.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

DEBOUNCE_SEC = 1.5


class CleanupPreviewRegistry:
    def __init__(self, debounce_sec: float = DEBOUNCE_SEC):
        self._debounce_sec = debounce_sec
        self._lock = threading.Lock()
        self._preview: dict[str, dict] = {}
        self._timer: threading.Timer | None = None
        self._source: Callable[[], tuple] | None = None

    def configure(self, source: Callable[[], tuple]) -> None:
        """(clips_dir, retention_cfg) 를 매번 새로 구해오는 함수를 등록한다.

        설정 파일을 그때그때 다시 읽는 함수를 넘기면, 사용자가 옵션을 바꿔도 재시작
        없이 다음 계산부터 반영된다(pipeline/cleanup.py::make_cleanup_runner 와 같은 방식).
        """
        with self._lock:
            self._source = source

    def notify_clips_changed(self) -> None:
        """클립이 바뀔 때마다 부른다. 디바운스 창 안에 여러 번 와도 마지막 한 번만 계산한다."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            timer = threading.Timer(self._debounce_sec, self._recompute)
            timer.daemon = True
            self._timer = timer
            timer.start()

    def recompute_now(self) -> None:
        """디바운스 없이 즉시 계산한다(앱 시작 시 1회 등)."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        self._recompute()

    def _recompute(self) -> None:
        with self._lock:
            source = self._source
        if source is None:
            return
        clips_dir, cfg = source()
        from lumia_briefing_room.pipeline.cleanup import cleanup_preview

        preview = cleanup_preview(clips_dir, cfg)
        with self._lock:
            self._preview = preview

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            return dict(self._preview)


registry = CleanupPreviewRegistry()
