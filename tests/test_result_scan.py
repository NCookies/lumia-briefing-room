from dataclasses import replace

from lumia_briefing_room.video.segments import SegmentRange

import numpy as np

from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.detect.scoreboard import BoardRow
from lumia_briefing_room.pipeline.result_scan import (
    EndScreens,
    attach_board,
    contiguous_segments,
    scan_for_result,
    scan_forward_for_result,
)

RESULT = ResultScreen(placement=4, total=7, match_type="rank", match_label="랭크", outcome="실험 종료", nickname="나")


def frames(*tags):
    return [(n, np.full((2, 2, 3), tag, dtype=np.uint8)) for n, tag in enumerate(tags, start=1)]


def make_read(calls):
    def read(frame):
        calls.append(int(frame[0, 0, 0]))
        return RESULT if int(frame[0, 0, 0]) == 9 else None

    return read


def test_scan_walks_backwards_from_the_last_frame_and_stops_at_first_hit():
    calls = []

    result = scan_for_result(frames(1, 9, 2, 3), make_read(calls), is_ingame=lambda f: False)

    assert result.result == RESULT
    assert calls == [3, 2, 9]


def test_scan_skips_ingame_frames_without_running_ocr():
    calls = []

    result = scan_for_result(frames(9, 1, 1), make_read(calls), is_ingame=lambda f: int(f[0, 0, 0]) == 1)

    assert result.result == RESULT
    assert calls == [9]


def test_scan_gives_up_after_max_frames():
    calls = []

    result = scan_for_result(frames(9, 1, 1, 1), make_read(calls), is_ingame=lambda f: False, max_frames=2)

    assert result.result is None
    assert calls == [1, 1]


def test_scan_returns_none_when_no_frame_matches():
    assert scan_for_result(frames(1, 2), make_read([]), is_ingame=lambda f: False).result is None


def batches(*groups):
    return iter([frames(*g) for g in groups])


def test_scan_forward_reads_batches_lazily_and_stops_at_first_hit():
    calls = []
    consumed = []

    def source():
        for group in [(1, 1), (1, 9), (2, 2)]:
            consumed.append(group)
            yield frames(*group)

    result = scan_forward_for_result(source(), make_read(calls), is_ingame=lambda f: int(f[0, 0, 0]) == 1)

    assert result.result == RESULT
    assert calls == [9]
    assert consumed == [(1, 1), (1, 9)]


def test_scan_forward_gives_up_after_max_ocr_attempts():
    calls = []

    result = scan_forward_for_result(
        batches((2, 2), (2, 2)), make_read(calls), is_ingame=lambda f: False, max_ocr=3
    )

    assert result.result is None
    assert len(calls) == 3


BOARD = [BoardRow(rank=1, nickname="나", character="마르티나")]


def test_scan_backwards_also_collects_the_scoreboard_seen_after_the_result_screen():
    boards = []

    def read_board(frame):
        boards.append(int(frame[0, 0, 0]))
        return BOARD if int(frame[0, 0, 0]) == 5 else None

    screens = scan_for_result(
        frames(9, 1, 5, 2), make_read([]), is_ingame=lambda f: False, read_board=read_board
    )

    assert screens.result == RESULT and screens.board == BOARD
    assert boards == [2, 5]


def test_scan_forward_keeps_looking_for_the_scoreboard_after_the_result_screen():
    def read_board(frame):
        return BOARD if int(frame[0, 0, 0]) == 5 else None

    screens = scan_forward_for_result(
        batches((1, 9, 2), (3, 5, 4)), make_read([]), is_ingame=lambda f: False, read_board=read_board
    )

    assert screens.result == RESULT and screens.board == BOARD


def test_scan_forward_stops_looking_for_the_scoreboard_after_max_after_frames():
    screens = scan_forward_for_result(
        batches((9, 2, 2), (2, 2, 5)), make_read([]), is_ingame=lambda f: False,
        read_board=lambda f: BOARD if int(f[0, 0, 0]) == 5 else None, max_after=3,
    )

    assert screens.result == RESULT and screens.board is None


def test_attach_board_adds_teammates_and_fills_a_missing_character():
    board = [
        BoardRow(rank=1, nickname="팀원가", character="루치아"),
        BoardRow(rank=1, nickname="나", character="마르티나"),
        BoardRow(rank=2, nickname="x", character="니키"),
    ]

    attached = attach_board(EndScreens(RESULT, board))

    assert attached.teammates == [{"nickname": "팀원가", "character": "루치아"}]
    assert attached.character == "마르티나"


def test_attach_board_keeps_the_result_screen_character_and_ignores_unmatched_boards():
    with_char = replace(RESULT, character="마커스")
    board = [BoardRow(rank=1, nickname="나", character="마르티나")]

    assert attach_board(EndScreens(with_char, board)).character == "마커스"
    assert attach_board(EndScreens(RESULT, [BoardRow(rank=1, nickname="다른사람", character=None)])) == RESULT
    assert attach_board(EndScreens(RESULT, None)) == RESULT
    assert attach_board(EndScreens(None, board)) is None


def test_contiguous_segments_starts_right_after_the_last_clip():
    assert contiguous_segments([1, 2, 3, 4, 5], after=2, before=None) == [3, 4, 5]


def test_contiguous_segments_is_empty_when_the_footage_after_the_clip_was_already_deleted():
    assert contiguous_segments([2871, 2872, 2873], after=2544, before=None) == []


def test_contiguous_segments_stops_at_a_gap_and_at_the_next_game_start():
    assert contiguous_segments([3, 4, 5, 9, 10], after=2, before=None) == [3, 4, 5]
    assert contiguous_segments([3, 4, 5, 6, 7], after=2, before=6) == [3, 4, 5]
    assert contiguous_segments([], after=2, before=None) == []


def test_scan_window_reaches_past_the_logged_match_end_but_never_before_the_first_segment():
    from lumia_briefing_room.pipeline.result_scan import MAX_SCAN_FRAMES, RESULT_TAIL_SEGMENTS, scan_window

    first, last = scan_window(SegmentRange(first=10, last=974))

    assert last == 974 + RESULT_TAIL_SEGMENTS
    assert first == last - MAX_SCAN_FRAMES + 1
    assert scan_window(SegmentRange(first=10, last=20))[0] == 10


def test_attach_board_recovers_only_my_teammates_missing_a_character_never_other_teams():
    board = [
        BoardRow(rank=1, nickname="팀원가", character=None, y=245),
        BoardRow(rank=1, nickname="나", character="마르티나", y=347),
        BoardRow(rank=1, nickname="동료", character="루치아", y=442),
        BoardRow(rank=2, nickname="적1", character=None, y=540),
        BoardRow(rank=3, nickname="적2", character=None, y=640),
    ]
    asked = []

    def recover(row):
        asked.append(row.nickname)
        return "엘레나"

    attached = attach_board(EndScreens(RESULT, board), recover=recover)

    assert asked == ["팀원가"]
    assert attached.teammates == [{"nickname": "팀원가", "character": "엘레나"}, {"nickname": "동료", "character": "루치아"}]


def test_attach_board_skips_recovery_when_everyone_on_my_team_is_already_read():
    board = [BoardRow(rank=1, nickname="팀원가", character="루치아"), BoardRow(rank=1, nickname="나", character="마르티나")]

    attach_board(EndScreens(RESULT, board), recover=lambda row: (_ for _ in ()).throw(AssertionError("불필요한 재시도")))
