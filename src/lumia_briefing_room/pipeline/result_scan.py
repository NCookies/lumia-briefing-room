from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from lumia_briefing_room.detect.day import read_game_day
from lumia_briefing_room.detect.ocr import OcrReader, TextReader
from lumia_briefing_room.detect.phase import read_cobalt_phase
from lumia_briefing_room.detect.region import load_region_templates
from lumia_briefing_room.detect.result import ResultScreen, merge_results, read_result_screen
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.frames import extract_keyframe_frames
from lumia_briefing_room.video.segments import SegmentRange, existing_segment_numbers
from lumia_briefing_room.video.session import RecordingSession

log = logging.getLogger(__name__)

MAX_SCAN_FRAMES = 40
RESULT_TAIL_SEGMENTS = 8
FORWARD_BATCH = 20
FORWARD_MAX_BATCHES = 60
FORWARD_MAX_OCR = 600
MAX_VOTES = 3
VOTE_PATIENCE = 3

_reader: TextReader | None = None


def result_image_name(match_start: datetime) -> str:
    return f"{match_start:%Y%m%d_%H%M%S}_result.jpg"


def save_result_image(frame: np.ndarray, path: Path, *, width: int = 1280) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(frame)
    image.resize((width, round(image.height * width / image.width)), Image.LANCZOS).save(path, quality=85)


def get_reader() -> TextReader:
    global _reader
    if _reader is None:
        _reader = OcrReader()
    return _reader


@dataclass(frozen=True)
class EndScreens:
    result: ResultScreen | None
    at: int | float | None = None


class _Votes:
    """결과 화면으로 읽힌 프레임을 모아 합친다. 결과 화면이 끝났거나(연속 `patience` 장 못 읽음) `max_votes` 장을 모으면 끝."""

    def __init__(self, max_votes: int, patience: int) -> None:
        self.max_votes, self.patience = max_votes, patience
        self.reads: list[ResultScreen] = []
        self.at: int | float | None = None
        self._misses = 0

    def add(self, key: int | float, result: ResultScreen | None) -> None:
        if result is None:
            self._misses += 1
            return
        if not self.reads:
            self.at = key
        self.reads.append(result)
        self._misses = 0

    @property
    def done(self) -> bool:
        return bool(self.reads) and (len(self.reads) >= self.max_votes or self._misses >= self.patience)

    def outcome(self) -> EndScreens:
        return EndScreens(merge_results(self.reads), self.at)


def scan_for_result(
    frames: Iterable[tuple[int, np.ndarray]],
    read: Callable[[np.ndarray], ResultScreen | None],
    *,
    is_ingame: Callable[[np.ndarray], bool],
    max_frames: int = MAX_SCAN_FRAMES,
    max_votes: int = MAX_VOTES,
    patience: int = VOTE_PATIENCE,
) -> EndScreens:
    """경기 끝에서 거슬러 올라가며 결과 화면을 찾는다. 인게임 프레임은 OCR 없이 건너뛴다(OCR 이 프레임당 ~1초라서).

    첫 장에서 멈추지 않고 결과 화면이 이어지는 동안 몇 장을 더 읽어 항목별 다수결로 합친다(장마다 OCR 이 다른 곳을 틀린다).
    """
    votes = _Votes(max_votes, patience)
    for key, frame in list(frames)[::-1][:max_frames]:
        votes.add(key, None if is_ingame(frame) else read(frame))
        if votes.done:
            break
    return votes.outcome()


def scan_forward_for_result(
    batches: Iterable[list[tuple[int, np.ndarray]]],
    read: Callable[[np.ndarray], ResultScreen | None],
    *,
    is_ingame: Callable[[np.ndarray], bool],
    max_ocr: int = FORWARD_MAX_OCR,
    max_votes: int = MAX_VOTES,
    patience: int = VOTE_PATIENCE,
) -> EndScreens:
    votes = _Votes(max_votes, patience)
    attempts = 0
    for batch in batches:
        for key, frame in batch:
            if is_ingame(frame):
                votes.add(key, None)
            else:
                result = read(frame)
                votes.add(key, result)
                if result is None and not votes.reads:
                    attempts += 1
                    if attempts >= max_ocr:
                        return EndScreens(None)
            if votes.done:
                return votes.outcome()
    return votes.outcome()


def scan_window(seg_range: SegmentRange) -> tuple[int, int]:
    """결과 화면·순위표를 찾을 세그먼트 범위.

    로그의 로비 복귀 시각은 결과 화면이 뜬 직후(실측: 결과 화면이 종료 세그먼트와 같거나 1칸 뒤, 순위표 탭은 5칸 뒤까지)라서
    종료 시각에서 끝내면 그 화면들을 놓친다. 종료 뒤 RESULT_TAIL_SEGMENTS 칸까지 본다(아직 없는 세그먼트는 건너뛴다).
    """
    last = seg_range.last + RESULT_TAIL_SEGMENTS
    return max(seg_range.first, last - MAX_SCAN_FRAMES + 1), last


def make_is_ingame(
    profile: ResolutionProfile,
    day_templates: dict | None,
    phase_templates: dict | None = None,
) -> Callable[[np.ndarray], bool]:
    """plan.md §10 C2/C3: 배틀로얄은 일차, 코발트는 `Phase N` 이 읽히면 아직 게임 안이다.

    어느 모드인지 미리 알 필요 없이 `or` 로 합친다 - 실제 경기에서는 둘 중 하나만 읽힌다.
    """
    def is_ingame(frame: np.ndarray) -> bool:
        """`profile.crop()` 을 쓴다(`crop_roi` 아님) - 다시보기 1080p 프로필은 일차 ROI 가
        기준 해상도로 정규화돼야 본보기와 크기가 맞는다(§10-2, `phase_digit` 는 정규화가 없어
        둘 다 써도 결과가 같다).
        """
        if day_templates and read_game_day(profile.crop(frame, "day_digit"), day_templates) is not None:
            return True
        if phase_templates and "phase_digit" in profile.rois:
            return read_cobalt_phase(profile.crop(frame, "phase_digit"), phase_templates) is not None
        return False

    return is_ingame


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
    phase_templates = load_region_templates(profile.phase_templates) if profile.phase_templates else None

    tail_first, tail_last = scan_window(seg_range)
    numbers = existing_segment_numbers(session, 0, tail_first, tail_last)
    frames = extract_keyframe_frames(
        session, stream=0, segment_numbers=numbers, ffmpeg_path=ffmpeg_path, hwaccel=hwaccel
    )

    return scan_for_result(
        frames,
        lambda f: read_result_screen(f, profile, reader),
        is_ingame=make_is_ingame(profile, day_templates, phase_templates),
    ).result


def contiguous_segments(existing: list[int], *, after: int, before: int | None) -> list[int]:
    """마지막 클립 바로 뒤(after+1)부터 끊김 없이 이어진 세그먼트만 돌려준다. `before` 는 다음 경기 시작 세그먼트다.

    링버퍼가 그 경기 원본을 이미 지웠으면 남은 세그먼트가 한참 뒤에서 시작한다. 그걸 이어 훑으면 다른 경기의 결과 화면을 이 경기 것으로
    잘못 붙이므로, 바로 이어지지 않으면 빈 목록이다.
    """
    available = set(existing)
    numbers: list[int] = []
    n = after + 1
    while n in available and (before is None or n < before):
        numbers.append(n)
        n += 1
    return numbers


def find_result_after(
    session: RecordingSession,
    after_segment: int,
    *,
    ffmpeg_path: Path,
    profile: ResolutionProfile | None = None,
    reader: TextReader | None = None,
    hwaccel: str | None = None,
    before_segment: int | None = None,
) -> ResultScreen | None:
    """경기 끝 시각을 모를 때(이미 저장된 클립 보강) 마지막 클립 뒤에서 앞으로 훑어 첫 결과 화면을 찾는다.

    이 경기의 원본이 이어져 있는 구간(다음 경기 시작 `before_segment` 전까지)만 훑는다. 원본이 지워졌으면 None 이다.
    """
    profile = profile or ResolutionProfile.for_resolution(session.width, session.height)
    reader = reader or get_reader()
    day_templates = load_region_templates(profile.day_templates) if profile.day_templates else None
    phase_templates = load_region_templates(profile.phase_templates) if profile.phase_templates else None

    window_end = after_segment + FORWARD_BATCH * FORWARD_MAX_BATCHES
    numbers = contiguous_segments(
        existing_segment_numbers(session, 0, after_segment + 1, window_end), after=after_segment, before=before_segment
    )
    if not numbers:
        return None

    def batches():
        for i in range(0, len(numbers), FORWARD_BATCH):
            yield list(
                extract_keyframe_frames(
                    session, stream=0, segment_numbers=numbers[i : i + FORWARD_BATCH],
                    ffmpeg_path=ffmpeg_path, hwaccel=hwaccel,
                )
            )

    return scan_forward_for_result(
        batches(),
        lambda f: read_result_screen(f, profile, reader),
        is_ingame=make_is_ingame(profile, day_templates, phase_templates),
    ).result
