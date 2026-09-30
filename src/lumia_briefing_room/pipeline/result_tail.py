"""게임 끝부분을 초당 2장으로 촘촘히 읽어 결과 화면을 판독한다. (plan §2-5)

결과 화면은 2~3초만 떠 있을 수 있어 키프레임(3초 격자)으로는 0~1장밖에 안 걸린다. 게임마다 풀영상이 있으므로
그 끝부분을 읽고, 풀영상이 없으면 끝 세그먼트를 이어 붙인 임시 파일을 같은 방법으로 읽는다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from pathlib import Path

import numpy as np

from lumia_briefing_room.detect.ocr import TextReader
from lumia_briefing_room.detect.region import load_region_templates
from lumia_briefing_room.detect.result import ResultScreen, read_result_screen
from lumia_briefing_room.pipeline.result_scan import EndScreens, get_reader, make_is_ingame, scan_forward_for_result
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.frames import extract_tail_frames, write_merged_segment_file
from lumia_briefing_room.video.segments import SegmentRange, existing_segment_numbers
from lumia_briefing_room.video.session import RecordingSession
from lumia_briefing_room.video.vod import find_ffprobe, probe_video

log = logging.getLogger(__name__)

TAIL_SEC = 30.0
TAIL_FPS = 2.0
TAIL_SEGMENTS = 12


def end_screens_from_frames(
    frames: Iterable[tuple[int, np.ndarray]],
    read: Callable[[np.ndarray], ResultScreen | None],
    *,
    is_ingame: Callable[[np.ndarray], bool],
) -> EndScreens:
    """프레임을 한 장씩 흘려 읽는다(메모리는 프레임 한 장 분량). 결과 화면이 끝나면 더 디코딩하지 않는다. `at` 은 결과 화면이 처음 읽힌 프레임."""
    batches = ([frame] for frame in frames)
    try:
        return scan_forward_for_result(batches, read, is_ingame=is_ingame)
    finally:
        close = getattr(frames, "close", None)
        if close is not None:
            close()


def result_from_frames(
    frames: Iterable[tuple[int, np.ndarray]],
    read: Callable[[np.ndarray], ResultScreen | None],
    *,
    is_ingame: Callable[[np.ndarray], bool],
) -> ResultScreen | None:
    return end_screens_from_frames(frames, read, is_ingame=is_ingame).result


def find_result_in_video(
    video_path: Path,
    *,
    ffmpeg_path: Path,
    profile: ResolutionProfile | None = None,
    reader: TextReader | None = None,
    hwaccel: str | None = None,
    tail_sec: float | None = TAIL_SEC,
    fps: float = TAIL_FPS,
) -> ResultScreen | None:
    ffprobe_path = find_ffprobe(ffmpeg_path)
    if ffprobe_path is None:
        raise FileNotFoundError("ffprobe 를 찾을 수 없다")
    if profile is None:
        info = probe_video(video_path, ffprobe_path=ffprobe_path)
        profile = ResolutionProfile.for_resolution(info.width, info.height)
    reader = reader or get_reader()
    day_templates = load_region_templates(profile.day_templates) if profile.day_templates else None
    phase_templates = load_region_templates(profile.phase_templates) if profile.phase_templates else None

    return result_from_frames(
        extract_tail_frames(
            video_path, tail_sec=tail_sec, fps=fps, ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path, hwaccel=hwaccel
        ),
        lambda f: read_result_screen(f, profile, reader),
        is_ingame=make_is_ingame(profile, day_templates, phase_templates),
    )


def find_result_in_segments(
    session: RecordingSession,
    last_segment: int,
    *,
    ffmpeg_path: Path,
    tmp_dir: Path,
    profile: ResolutionProfile | None = None,
    reader: TextReader | None = None,
    hwaccel: str | None = None,
) -> ResultScreen | None:
    """풀영상이 없을 때: `last_segment` 로 끝나는 마지막 세그먼트들을 임시 파일로 이어 붙여 같은 방법으로 읽는다."""
    first = max(last_segment - TAIL_SEGMENTS + 1, 0)
    numbers = existing_segment_numbers(session, 0, first, last_segment)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    merged = tmp_dir / f"result_tail_{session.directory.name}_{last_segment}.mp4"
    try:
        if not write_merged_segment_file(session, 0, numbers, merged):
            return None
        return find_result_in_video(
            merged, ffmpeg_path=ffmpeg_path,
            profile=profile or ResolutionProfile.for_resolution(session.width, session.height),
            reader=reader, hwaccel=hwaccel, tail_sec=None,
        )
    finally:
        merged.unlink(missing_ok=True)
