"""스팀 녹화 세션을 화면만으로 훑어 게임(경기) 구간을 찾는다. (plan-backfill.md B2)

`Player.log` 에 남지 않은 과거 경기를 복구하는 데 쓴다. 프레임 판독과 게임 분할은 다시보기 분석(vod_games)을 그대로 쓰고,
여기서는 세션의 세그먼트를 읽어 판독을 캐시하고(이어하기), 게임 구간을 UTC 경계로 바꾼다.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.pipeline.vod_games import split_games
from lumia_briefing_room.pipeline.vod_store import StateCache
from lumia_briefing_room.recording_info import ETERNAL_RETURN_APP_ID

POST_GAME_SEC = 120.0
CHECKPOINT_FRAMES = 120
PROGRESS_EVERY_FRAMES = 20
_SESSION_FOLDER = re.compile(r"^bg_(\d+)_(\d{8})_(\d{6})$")

ReadFrame = Callable[[object, float], FrameState]
SourceFactory = Callable[[int], object]


class ScanCancelled(Exception):
    """사용자가 취소했다. 여기까지의 판독은 캐시에 남아 이어할 수 있다."""


@dataclass(frozen=True)
class GameWindow:
    index: int
    hud_start_utc: datetime
    hud_end_utc: datetime
    end_utc: datetime
    confidence: float
    cut_at_start: bool
    still_running: bool

    @property
    def start_utc(self) -> datetime:
        return self.hud_start_utc


def window_key(session_name: str, window: GameWindow) -> str:
    return f"scan|{session_name}|{window.hud_start_utc.strftime('%Y%m%dT%H%M%S')}"


def list_session_dirs(recording_root: Path, app_id: int = ETERNAL_RETURN_APP_ID) -> list[Path]:
    """이터널 리턴 세션 폴더를 오래된 것부터 돌려준다. 다른 게임 세션은 뺀다."""
    try:
        entries = list(Path(recording_root).iterdir())
    except OSError:
        return []
    found = []
    for entry in entries:
        match = _SESSION_FOLDER.match(entry.name)
        if match and entry.is_dir() and int(match.group(1)) == app_id:
            found.append((match.group(2) + match.group(3), entry))
    return [entry for _, entry in sorted(found)]


def windows_from_states(
    states: list[FrameState],
    *,
    session_start_utc: datetime,
    seg_sec: float,
    post_game_sec: float = POST_GAME_SEC,
) -> list[GameWindow]:
    """프레임 판독을 게임 구간으로 나눠 UTC 경계로 바꾼다.

    시작은 인게임 HUD 가 처음 보인 시각(로딩이 끝난 뒤라 로그의 시작보다 늦다), 끝은 결과 화면이 나올 시간을 위해
    마지막 인게임 프레임 뒤로 여유를 주되 다음 경기 시작·녹화 끝을 넘지 않는다.
    """
    if not states:
        return []
    first_t, last_t = states[0].t, states[-1].t
    spans = split_games(states)

    def at(sec: float) -> datetime:
        return session_start_utc + timedelta(seconds=sec)

    windows = []
    for i, span in enumerate(spans):
        next_start = spans[i + 1].start if i + 1 < len(spans) else None
        end = min(span.end + post_game_sec, last_t + seg_sec)
        if next_start is not None:
            end = min(end, next_start)
        windows.append(
            GameWindow(
                index=span.index,
                hud_start_utc=at(span.start),
                hud_end_utc=at(span.end),
                end_utc=at(end),
                confidence=span.confidence,
                cut_at_start=span.start <= first_t + seg_sec,
                still_running=span.end >= last_t - seg_sec,
            )
        )
    return windows


def scan_frames(
    cache: StateCache,
    *,
    segment_numbers: list[int],
    seg_sec: float,
    source_factory: SourceFactory,
    read_frame: ReadFrame,
    cancel: threading.Event | None = None,
    on_progress: Callable[[float, str], None] | None = None,
) -> list[FrameState]:
    """세그먼트마다 키프레임 한 장씩 판독해 캐시에 이어 쓴다. 캐시가 있으면 그 다음 세그먼트부터 이어간다.

    링버퍼가 이미 지운 세그먼트는 `segment_numbers` 에 없으므로 건너뛴다.
    """
    states = cache.load()
    if not segment_numbers:
        return states

    first, last = segment_numbers[0], segment_numbers[-1]
    resume_from = first
    if states:
        resume_from = max(first, int(round(states[-1].t / seg_sec)) + 2)
    if resume_from > last:
        return states

    total = max(1, last - first + 1)
    pending: list[FrameState] = []
    generator = source_factory(resume_from).frames()

    def flush() -> None:
        nonlocal pending
        cache.append(pending)
        states.extend(pending)
        pending = []

    try:
        for count, (t, frame) in enumerate(generator, start=1):
            if cancel is not None and cancel.is_set():
                flush()
                raise ScanCancelled()
            pending.append(read_frame(frame, t))
            if len(pending) >= CHECKPOINT_FRAMES:
                flush()
            if on_progress is not None and count % PROGRESS_EVERY_FRAMES == 0:
                done = int(round(t / seg_sec)) + 1 - first
                on_progress(min(1.0, done / total), f"{t / 60:.0f}분 지점")
    finally:
        generator.close()
    flush()
    if on_progress is not None:
        on_progress(1.0, "")
    return states
