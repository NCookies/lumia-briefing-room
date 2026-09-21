from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from pathlib import Path

import numpy as np

from lumia_briefing_room.detect.day import read_game_day
from lumia_briefing_room.detect.ocr import OcrReader, TextReader
from lumia_briefing_room.detect.region import load_region_templates
from lumia_briefing_room.detect.result import ResultScreen, read_result_screen
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.frames import crop_roi, extract_keyframe_frames
from lumia_briefing_room.video.segments import SegmentRange, existing_segment_numbers
from lumia_briefing_room.video.session import RecordingSession

log = logging.getLogger(__name__)

MAX_SCAN_FRAMES = 40
FORWARD_BATCH = 20
FORWARD_MAX_BATCHES = 60
FORWARD_MAX_OCR = 30

_reader: TextReader | None = None


def get_reader() -> TextReader:
    global _reader
    if _reader is None:
        _reader = OcrReader()
    return _reader


def scan_for_result(
    frames: Iterable[tuple[int, np.ndarray]],
    read: Callable[[np.ndarray], ResultScreen | None],
    *,
    is_ingame: Callable[[np.ndarray], bool],
    max_frames: int = MAX_SCAN_FRAMES,
) -> ResultScreen | None:
    """경기 끝에서 거슬러 올라가며 결과 화면을 찾는다. 인게임 프레임은 OCR 없이 건너뛴다(OCR 이 프레임당 ~1초라서)."""
    for _, frame in list(frames)[::-1][:max_frames]:
        if is_ingame(frame):
            continue
        result = read(frame)
        if result is not None:
            return result
    return None


def scan_forward_for_result(
    batches: Iterable[list[tuple[int, np.ndarray]]],
    read: Callable[[np.ndarray], ResultScreen | None],
    *,
    is_ingame: Callable[[np.ndarray], bool],
    max_ocr: int = FORWARD_MAX_OCR,
) -> ResultScreen | None:
    attempts = 0
    for batch in batches:
        for _, frame in batch:
            if is_ingame(frame):
                continue
            result = read(frame)
            if result is not None:
                return result
            attempts += 1
            if attempts >= max_ocr:
                return None
    return None


def find_result_screen(
    session: RecordingSession,
    seg_range: SegmentRange,
    *,
    ffmpeg_path: Path,
    profile: ResolutionProfile | None = None,
    reader: TextReader | None = None,
    hwaccel: str | None = None,
) -> ResultScreen | None:
    profile = profile or ResolutionProfile.for_resolution(session.width, session.height)
    reader = reader or get_reader()
    day_templates = load_region_templates(profile.day_templates) if profile.day_templates else None

    tail_first = max(seg_range.first, seg_range.last - MAX_SCAN_FRAMES + 1)
    numbers = existing_segment_numbers(session, 0, tail_first, seg_range.last)
    frames = extract_keyframe_frames(
        session, stream=0, segment_numbers=numbers, ffmpeg_path=ffmpeg_path, hwaccel=hwaccel
    )

    def is_ingame(frame: np.ndarray) -> bool:
        if day_templates is None:
            return False
        return read_game_day(crop_roi(frame, profile.rois["day_digit"]), day_templates) is not None

    return scan_for_result(
        frames, lambda f: read_result_screen(f, profile, reader), is_ingame=is_ingame
    )


def find_result_after(
    session: RecordingSession,
    after_segment: int,
    *,
    ffmpeg_path: Path,
    profile: ResolutionProfile | None = None,
    reader: TextReader | None = None,
    hwaccel: str | None = None,
) -> ResultScreen | None:
    """경기 끝 시각을 모를 때(이미 저장된 클립 보강) 마지막 클립 뒤에서 앞으로 훑어 첫 결과 화면을 찾는다."""
    profile = profile or ResolutionProfile.for_resolution(session.width, session.height)
    reader = reader or get_reader()
    day_templates = load_region_templates(profile.day_templates) if profile.day_templates else None

    last_existing = max(existing_segment_numbers(session, 0, after_segment, after_segment + FORWARD_BATCH * FORWARD_MAX_BATCHES), default=None)
    if last_existing is None:
        return None
    numbers = existing_segment_numbers(session, 0, after_segment + 1, last_existing)

    def batches():
        for i in range(0, len(numbers), FORWARD_BATCH):
            yield list(
                extract_keyframe_frames(
                    session, stream=0, segment_numbers=numbers[i : i + FORWARD_BATCH],
                    ffmpeg_path=ffmpeg_path, hwaccel=hwaccel,
                )
            )

    def is_ingame(frame: np.ndarray) -> bool:
        if day_templates is None:
            return False
        return read_game_day(crop_roi(frame, profile.rois["day_digit"]), day_templates) is not None

    return scan_forward_for_result(
        batches(), lambda f: read_result_screen(f, profile, reader), is_ingame=is_ingame
    )
