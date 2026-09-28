from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

from lumia_briefing_room.detect.cobalt_result import read_cobalt_result_screen, to_result_screen
from lumia_briefing_room.detect.ocr import TextReader
from lumia_briefing_room.detect.region import load_region_templates
from lumia_briefing_room.detect.result import ResultScreen, read_result_screen
from lumia_briefing_room.detect.scoreboard import BoardRow
from lumia_briefing_room.pipeline.result_scan import (
    FORWARD_BATCH,
    _board_reader,
    attach_board,
    get_reader,
    make_is_ingame,
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
    read_board: Callable[[np.ndarray], list[BoardRow] | None] | None = None,
    recover: Callable[[BoardRow], str | None] | None = None,
    window_sec: float = RESULT_WINDOW_SEC,
) -> ResultScreen | None:
    """게임이 끝난 뒤(다음 게임 시작 전, 최대 window_sec)를 앞으로 훑어 결과 화면·순위표를 찾는다.

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
        screens = scan_forward_for_result(
            batches(), read, is_ingame=is_ingame, read_board=read_board
        )
    finally:
        frames.close()
    return attach_board(screens, recover=recover)


def find_vod_result(
    video_path: Path,
    span: GameSpan,
    next_start: float | None,
    *,
    ffmpeg_path: Path,
    profile: ResolutionProfile,
    reader: TextReader | None = None,
    hwaccel: str | None = None,
    read_boards: bool = True,
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
    read_board = recover = None
    if read_boards:
        read_board, recover = _board_reader(profile, reader)
    return scan_game_end(
        factory, span, next_start,
        read=read,
        is_ingame=is_ingame, read_board=read_board, recover=recover,
    )
