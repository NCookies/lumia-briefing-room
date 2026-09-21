from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from lumia_briefing_room.detect.character import load_characters
from lumia_briefing_room.detect.day import read_game_day
from lumia_briefing_room.detect.ocr import OcrReader, TextReader
from lumia_briefing_room.detect.region import load_region_templates
from lumia_briefing_room.detect.result import ResultScreen, read_result_screen
from lumia_briefing_room.detect.scoreboard import BoardRow, find_team, read_scoreboard, recover_character
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.frames import crop_roi, extract_keyframe_frames
from lumia_briefing_room.video.segments import SegmentRange, existing_segment_numbers
from lumia_briefing_room.video.session import RecordingSession

log = logging.getLogger(__name__)

MAX_SCAN_FRAMES = 40
RESULT_TAIL_SEGMENTS = 8
FORWARD_BATCH = 20
FORWARD_MAX_BATCHES = 60
FORWARD_MAX_OCR = 600
FORWARD_BOARD_FRAMES = 45

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
    board: list[BoardRow] | None


def scan_for_result(
    frames: Iterable[tuple[int, np.ndarray]],
    read: Callable[[np.ndarray], ResultScreen | None],
    *,
    is_ingame: Callable[[np.ndarray], bool],
    max_frames: int = MAX_SCAN_FRAMES,
    read_board: Callable[[np.ndarray], list[BoardRow] | None] | None = None,
) -> EndScreens:
    """경기 끝에서 거슬러 올라가며 결과 화면과 순위표를 찾는다. 인게임 프레임은 OCR 없이 건너뛴다(OCR 이 프레임당 ~1초라서).

    순위표 탭은 결과 화면 뒤에 나오므로 거슬러 오르는 동안 결과 화면보다 먼저 만난다. 결과 화면을 찾으면 멈춘다.
    """
    board = None
    for _, frame in list(frames)[::-1][:max_frames]:
        if is_ingame(frame):
            continue
        if read_board is not None and board is None:
            board = read_board(frame)
        result = read(frame)
        if result is not None:
            return EndScreens(result, board)
    return EndScreens(None, board)


def scan_forward_for_result(
    batches: Iterable[list[tuple[int, np.ndarray]]],
    read: Callable[[np.ndarray], ResultScreen | None],
    *,
    is_ingame: Callable[[np.ndarray], bool],
    max_ocr: int = FORWARD_MAX_OCR,
    read_board: Callable[[np.ndarray], list[BoardRow] | None] | None = None,
    max_after: int = FORWARD_BOARD_FRAMES,
) -> EndScreens:
    result: ResultScreen | None = None
    board: list[BoardRow] | None = None
    attempts = after = 0
    for batch in batches:
        for _, frame in batch:
            if is_ingame(frame):
                continue
            if result is None:
                result = read(frame)
                if result is None:
                    attempts += 1
                    if attempts >= max_ocr:
                        return EndScreens(None, None)
                    continue
            if read_board is not None and board is None:
                board = read_board(frame)
            after += 1
            if board is not None or read_board is None or after >= max_after:
                return EndScreens(result, board)
    return EndScreens(result, board)


def attach_board(screens: EndScreens, *, recover: Callable[[BoardRow], str | None] | None = None) -> ResultScreen | None:
    """순위표에서 내 팀을 찾아 결과에 붙인다. 결과 화면에서 못 읽은 내 캐릭터도 표에서 채운다.

    `recover` 는 캐릭터 이름을 못 읽은 행을 비싼 재시도로 다시 읽는다. 내 팀원(과 결과 화면에서 못 읽은 내 행)에게만 부른다.
    """
    result = screens.result
    if result is None or not screens.board:
        return result
    team = find_team(screens.board, result.nickname)
    if team is None:
        return result
    me, mates = team
    if recover is not None:
        mates = [replace(m, character=recover(m)) if m.character is None else m for m in mates]
        if not result.character and me.character is None:
            me = replace(me, character=recover(me))
    return replace(
        result,
        character=result.character or me.character,
        teammates=[{"nickname": m.nickname, "character": m.character} for m in mates],
    )


def _board_reader(profile, reader):
    """순위표를 재시도 없이 읽고, 나중에 팀원만 다시 읽을 수 있게 그 프레임을 기억한다."""
    seen: dict[str, np.ndarray] = {}

    def read_board(frame: np.ndarray):
        rows = read_scoreboard(frame, profile, reader, _roster(), recover=False)
        if rows:
            seen["frame"] = frame
        return rows

    def recover(row: BoardRow) -> str | None:
        frame = seen.get("frame")
        return recover_character(frame, row.y, _roster(), reader) if frame is not None else None

    return read_board, recover


@lru_cache(maxsize=1)
def _roster() -> list[str]:
    return sorted(set(load_characters().values()))


def scan_window(seg_range: SegmentRange) -> tuple[int, int]:
    """결과 화면·순위표를 찾을 세그먼트 범위.

    로그의 로비 복귀 시각은 결과 화면이 뜬 직후(실측: 결과 화면이 종료 세그먼트와 같거나 1칸 뒤, 순위표 탭은 5칸 뒤까지)라서
    종료 시각에서 끝내면 그 화면들을 놓친다. 종료 뒤 RESULT_TAIL_SEGMENTS 칸까지 본다(아직 없는 세그먼트는 건너뛴다).
    """
    last = seg_range.last + RESULT_TAIL_SEGMENTS
    return max(seg_range.first, last - MAX_SCAN_FRAMES + 1), last


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

    tail_first, tail_last = scan_window(seg_range)
    numbers = existing_segment_numbers(session, 0, tail_first, tail_last)
    frames = extract_keyframe_frames(
        session, stream=0, segment_numbers=numbers, ffmpeg_path=ffmpeg_path, hwaccel=hwaccel
    )

    def is_ingame(frame: np.ndarray) -> bool:
        if day_templates is None:
            return False
        return read_game_day(crop_roi(frame, profile.rois["day_digit"]), day_templates) is not None

    read_board, recover = _board_reader(profile, reader)
    return attach_board(
        scan_for_result(
            frames,
            lambda f: read_result_screen(f, profile, reader),
            is_ingame=is_ingame,
            read_board=read_board,
        ),
        recover=recover,
    )


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

    def is_ingame(frame: np.ndarray) -> bool:
        if day_templates is None:
            return False
        return read_game_day(crop_roi(frame, profile.rois["day_digit"]), day_templates) is not None

    read_board, recover = _board_reader(profile, reader)
    return attach_board(
        scan_forward_for_result(
            batches(),
            lambda f: read_result_screen(f, profile, reader),
            is_ingame=is_ingame,
            read_board=read_board,
        ),
        recover=recover,
    )
