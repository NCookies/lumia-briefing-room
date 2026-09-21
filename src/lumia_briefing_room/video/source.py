from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from lumia_briefing_room.video.frames import extract_keyframe_frames
from lumia_briefing_room.video.segments import SegmentRange, existing_segment_numbers
from lumia_briefing_room.video.session import RecordingSession


@runtime_checkable
class FrameSource(Protocol):
    """검출기에 프레임을 내주는 공급자. 스팀 세그먼트든 영상 파일이든 (시각 초, 프레임) 만 내주면 된다."""

    width: int
    height: int

    def frames(self) -> Iterator[tuple[float, np.ndarray]]: ...

    def gaps(self) -> list[tuple[float, float]]: ...


class SteamSegmentSource:
    """스팀 배경 녹화의 세그먼트 범위. 세그먼트마다 키프레임 1장이고, 지워진 세그먼트는 gap 으로 알린다."""

    def __init__(
        self,
        session: RecordingSession,
        seg_range: SegmentRange,
        *,
        stream: int = 0,
        ffmpeg_path: Path,
        hwaccel: str | None = None,
    ) -> None:
        self._session = session
        self._seg_range = seg_range
        self._stream = stream
        self._ffmpeg_path = ffmpeg_path
        self._hwaccel = hwaccel
        self.width = session.width
        self.height = session.height
        self._existing = existing_segment_numbers(
            session, stream, seg_range.first, seg_range.last
        )

    def frames(self) -> Iterator[tuple[float, np.ndarray]]:
        duration = self._session.segment_duration_sec
        for seg_num, frame in extract_keyframe_frames(
            self._session,
            stream=self._stream,
            segment_numbers=self._existing,
            ffmpeg_path=self._ffmpeg_path,
            hwaccel=self._hwaccel,
        ):
            yield (seg_num - 1) * duration, frame

    def gaps(self) -> list[tuple[float, float]]:
        duration = self._session.segment_duration_sec
        return [
            ((g0 - 1) * duration, g1 * duration)
            for g0, g1 in self._seg_range.gaps(self._existing)
        ]
