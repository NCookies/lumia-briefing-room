from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

from lumia_briefing_room.detect.day import read_game_day
from lumia_briefing_room.detect.ocr import TextReader
from lumia_briefing_room.detect.region import load_region_templates
from lumia_briefing_room.detect.result import ResultScreen, read_result_screen
from lumia_briefing_room.pipeline.result_scan import (
    FORWARD_BATCH,
    get_reader,
    scan_forward_for_result,
)
from lumia_briefing_room.pipeline.vod_games import GameSpan
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.source import FrameSource
from lumia_briefing_room.video.vod import VodFileSource, find_ffprobe

RESULT_WINDOW_SEC = 300.0

SourceFactory = Callable[[float, float], FrameSource]


def scan_game_end(
    source_factory: SourceFactory,
    span: GameSpan,
    next_start: float | None,
    *,
    read: Callable[[np.ndarray], ResultScreen | None],
    is_ingame: Callable[[np.ndarray], bool],
    window_sec: float = RESULT_WINDOW_SEC,
) -> ResultScreen | None:
    """게임이 끝난 뒤(다음 게임 시작 전, 최대 window_sec)를 앞으로 훑어 결과 화면을 찾는다.

    결과 화면을 찾으면 멈추고 영상 읽기를 닫는다. 결과 화면을 안 본 채 나간 게임은 None 이다.
    """
    end = span.end + window_sec
    if next_start is not None:
        end = min(end, next_start)
    frames = source_factory(span.end, end).frames()

    def batches():
        batch: list[tuple[int, np.ndarray]] = []
        for i, (_, frame) in enumerate(frames):
            batch.append((i, frame))
            if len(batch) >= FORWARD_BATCH:
                yield batch
                batch = []
        if batch:
            yield batch

    try:
        return scan_forward_for_result(batches(), read, is_ingame=is_ingame).result
    finally:
        frames.close()


def find_vod_result(
    video_path: Path,
    span: GameSpan,
    next_start: float | None,
    *,
    ffmpeg_path: Path,
    profile: ResolutionProfile,
    reader: TextReader | None = None,
    hwaccel: str | None = None,
) -> ResultScreen | None:
    reader = reader or get_reader()
    ffprobe_path = find_ffprobe(ffmpeg_path)
    day_templates = load_region_templates(profile.day_templates) if profile.day_templates else None

    def factory(start: float, end: float) -> FrameSource:
        return VodFileSource(
            video_path, ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path,
            start_sec=start, end_sec=end, hwaccel=hwaccel,
        )

    def is_ingame(frame: np.ndarray) -> bool:
        if day_templates is None:
            return False
        return read_game_day(profile.crop(frame, "day_digit"), day_templates) is not None

    return scan_game_end(
        factory, span, next_start,
        read=lambda f: read_result_screen(f, profile, reader),
        is_ingame=is_ingame,
    )
