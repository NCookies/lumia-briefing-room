from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path

import numpy as np

from lumia_briefing_room.detect.cobalt_result import read_cobalt_result_screen, to_result_screen
from lumia_briefing_room.detect.ocr import TextReader
from lumia_briefing_room.detect.region import load_region_templates
from lumia_briefing_room.detect.result import ResultScreen, read_result_screen
from lumia_briefing_room.pipeline.result_scan import (
    FORWARD_BATCH,
    get_reader,
    make_is_ingame,
    scan_forward_for_result,
)
from lumia_briefing_room.pipeline.result_tail import end_screens_from_frames
from lumia_briefing_room.pipeline.vod_games import GameSpan
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.source import FrameSource
from lumia_briefing_room.video.vod import VodFileSource, find_ffprobe

RESULT_WINDOW_SEC = 300.0
DENSE_FPS = 2.0
DENSE_BEFORE_SEC = 3.0
DENSE_AFTER_SEC = 12.0
DENSE_PROBE_SEC = 30.0

SourceFactory = Callable[[float, float], FrameSource]


def scan_game_end(
    source_factory: SourceFactory,
    span: GameSpan,
    next_start: float | None,
    *,
    read: Callable[[np.ndarray], ResultScreen | None],
    is_ingame: Callable[[np.ndarray], bool],
    window_sec: float = RESULT_WINDOW_SEC,
    dense_factory: SourceFactory | None = None,
) -> ResultScreen | None:
    """게임이 끝난 뒤(다음 게임 시작 전, 최대 window_sec)를 앞으로 훑어 결과 화면을 찾는다.

    키프레임만 읽는 훑기는 빠르지만 결과 화면이 키프레임 사이에 끼면 놓치거나 한두 장만 잡힌다. `dense_factory`(초당 여러 장으로
    전부 디코딩하는 읽기)가 있으면, 훑기가 찾은 자리 앞뒤를 촘촘히 다시 읽어 다수결로 정한다. 훑기가 못 찾았으면 게임 끝 직후
    DENSE_PROBE_SEC 초를 촘촘히 읽어 본다. 결과 화면을 안 본 채 나간 게임은 None 이다.

    돌려주는 결과의 `t` 는 결과 화면이 처음 읽힌 영상 시각이다(풀영상 끝을 정하는 기준).
    """
    end = span.end + window_sec
    if next_start is not None:
        end = min(end, next_start)
    frames = source_factory(span.end, end).frames()

    def batches():
        batch: list[tuple[float, np.ndarray]] = []
        for t, frame in frames:
            batch.append((t, frame))
            if len(batch) >= FORWARD_BATCH:
                yield batch
                batch = []
        if batch:
            yield batch

    try:
        sparse = scan_forward_for_result(batches(), read, is_ingame=is_ingame)
    finally:
        frames.close()
    if dense_factory is None:
        return _with_time(sparse.result, sparse.at)

    if sparse.result is not None:
        start, stop = max(span.end, sparse.at - DENSE_BEFORE_SEC), min(end, sparse.at + DENSE_AFTER_SEC)
    else:
        start, stop = span.end, min(end, span.end + DENSE_PROBE_SEC)
    if stop <= start:
        return _with_time(sparse.result, sparse.at)
    dense = end_screens_from_frames(dense_factory(start, stop).frames(), read, is_ingame=is_ingame)
    if dense.result is not None:
        return _with_time(dense.result, dense.at)
    return _with_time(sparse.result, sparse.at)


def _with_time(result: ResultScreen | None, at: float | int | None) -> ResultScreen | None:
    if result is None or at is None:
        return result
    return dataclasses.replace(result, t=float(at))


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
    phase_templates = load_region_templates(profile.phase_templates) if profile.phase_templates else None
    outcome_templates = (
        load_region_templates(profile.cobalt_outcome_templates) if profile.cobalt_outcome_templates else None
    )

    def factory(start: float, end: float) -> FrameSource:
        return VodFileSource(
            video_path, ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path,
            start_sec=start, end_sec=end, hwaccel=hwaccel,
        )

    def dense_factory(start: float, end: float) -> FrameSource:
        return VodFileSource(
            video_path, ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path,
            start_sec=start, end_sec=end, hwaccel=hwaccel, fps=DENSE_FPS,
        )

    def read(frame: np.ndarray) -> ResultScreen | None:
        """plan.md §10 C3: 배틀로얄 결과 화면을 먼저 찾고, 없으면 코발트 승패 화면을 본다.

        둘 다 못 찾으면(로비·로딩 등) None - 어느 모드인지 미리 알 필요 없다.
        """
        result = read_result_screen(frame, profile, reader)
        if result is not None:
            return result
        cobalt = read_cobalt_result_screen(frame, profile, reader, outcome_templates)
        return to_result_screen(cobalt) if cobalt is not None else None

    is_ingame = make_is_ingame(profile, day_templates, phase_templates)
    return scan_game_end(
        factory, span, next_start,
        read=read,
        is_ingame=is_ingame,
        dense_factory=dense_factory,
    )
