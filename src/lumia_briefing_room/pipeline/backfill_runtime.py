"""과거 경기 복구(backfill)의 실제 부품: 세션 스캐너와 경기 처리기. (plan-backfill.md B4)

backfill.py 의 실행기는 이 둘을 주입받는다 — 테스트는 가짜로, 앱은 여기 있는 진짜로 돌린다.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from collections.abc import Callable
from pathlib import Path

from lumia_briefing_room.config import Config
from lumia_briefing_room.detect.match import DetectionCancelled
from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.pipeline.backfill import GameCancelled
from lumia_briefing_room.pipeline.clip import ClipCutError
from lumia_briefing_room.pipeline.nickname import learn_nickname
from lumia_briefing_room.pipeline.orchestrator import process_match
from lumia_briefing_room.pipeline.session_scan import (
    POST_GAME_SEC,
    GameWindow,
    list_session_dirs,
    scan_frames,
    windows_from_states,
)
from lumia_briefing_room.pipeline.vod_analyze import ANALYSIS_VERSION, _default_reader
from lumia_briefing_room.pipeline.vod_store import StateCache
from lumia_briefing_room.video.segments import SegmentRange, existing_segment_numbers
from lumia_briefing_room.video.session import RecordingSession, SessionParseError
from lumia_briefing_room.video.source import SteamSegmentSource

log = logging.getLogger("lumia_briefing_room.backfill")

MAX_SEGMENT_NUMBER = 10**7


def staging_config(cfg: Config) -> Config:
    """스테이징에 만든 썸네일이 실제 클립 폴더로 새어 나가지 않게, 썸네일 위치 오버라이드를 끈다."""
    return dataclasses.replace(cfg, paths=dataclasses.replace(cfg.paths, thumbnails=None))


def alive_states(states: list[FrameState], *, first_segment: int, seg_sec: float) -> list[FrameState]:
    """링버퍼가 이미 지운 구간의 캐시된 판독을 버린다. 그 구간의 경기는 클립을 만들 수 없다."""
    oldest = (first_segment - 1) * seg_sec
    return [s for s in states if s.t >= oldest - 1e-6]


class SteamSessionScanner:
    def __init__(
        self,
        recording_root: Path,
        ffmpeg_path: Path,
        *,
        state_dir: Path,
        hwaccel: str | None = None,
        post_game_sec: float = POST_GAME_SEC,
    ) -> None:
        self._root = recording_root
        self._ffmpeg = ffmpeg_path
        self._cache_dir = state_dir / f"scan-v{ANALYSIS_VERSION}"
        self._hwaccel = hwaccel
        self._post_game_sec = post_game_sec

    def list_sessions(self) -> list[Path]:
        return list_session_dirs(self._root)

    def scan(
        self, session_dir: Path, cancel: threading.Event | None, on_progress: Callable[[float, str], None]
    ) -> list[GameWindow]:
        try:
            session = RecordingSession.load(session_dir)
        except (SessionParseError, OSError, ValueError, TypeError) as exc:
            log.warning("세션을 읽지 못해 건너뛴다: %s (%s)", session_dir.name, exc)
            return []

        numbers = existing_segment_numbers(session, 0, 1, MAX_SEGMENT_NUMBER)
        if not numbers:
            return []
        seg = session.segment_duration_sec
        cache = StateCache(self._cache_dir / f"{session_dir.name}.states.jsonl.gz")
        read_frame = _default_reader(session.width, session.height)

        def source_factory(first: int):
            return SteamSegmentSource(
                session, SegmentRange(first, numbers[-1]), ffmpeg_path=self._ffmpeg, hwaccel=self._hwaccel
            )

        states = scan_frames(
            cache, segment_numbers=numbers, seg_sec=seg, source_factory=source_factory,
            read_frame=read_frame, cancel=cancel, on_progress=on_progress,
        )
        return windows_from_states(
            alive_states(states, first_segment=numbers[0], seg_sec=seg),
            session_start_utc=session.start_utc, seg_sec=seg, post_game_sec=self._post_game_sec,
        )


def make_process_window(
    cfg: Config,
    ffmpeg_path: Path,
    *,
    game_mode: str,
    k_templates: dict | None,
    a_templates: dict | None,
    hwaccel: str | None,
    config_path: Path | None,
) -> Callable[[Path, GameWindow, Path, threading.Event | None], list[Path]]:
    staged = staging_config(cfg)

    def process(
        session_dir: Path, window: GameWindow, staging: Path, cancel: threading.Event | None
    ) -> list[Path]:
        session = RecordingSession.load(session_dir)
        try:
            return process_match(
                session, window.hud_start_utc, window.end_utc, staged,
                ffmpeg_path=ffmpeg_path, game_mode=game_mode,
                k_templates=k_templates, a_templates=a_templates, hwaccel=hwaccel,
                clips_dir=staging, cancel=cancel, result_search_from=window.hud_end_utc,
                on_result=lambda r: learn_nickname(config_path, r.nickname),
            )
        except DetectionCancelled as exc:
            raise GameCancelled() from exc
        except ClipCutError as exc:
            log.warning("클립 생성 실패(세그먼트 없음): %s", exc)
            return []

    return process
