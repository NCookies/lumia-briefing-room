from datetime import datetime, timedelta, timezone

import pytest

from lumia_briefing_room.pipeline.playerlog import (
    LogEvent,
    LogEventType,
    MatchBoundary,
    extract_matches,
    parse_line,
)

KST = timezone(timedelta(hours=9))

GAME_START_LINE = (
    "[INFO][DESKTOP-IFDC4S7][2026-09-19 22:15:57,595][1][LoadingView:Show:194] "
    "[PROFILE TIME][LOADING][GAME]"
)
LOBBY_RETURN_LINE = (
    "[INFO][DESKTOP-IFDC4S7][2026-09-19 22:25:12,137][1][LoadingView:Show:135] "
    "[PROFILE TIME][LOADING][LOBBY]"
)
UNRELATED_LINE = (
    "[INFO][DESKTOP-IFDC4S7][2026-09-19 22:16:45,957][1]"
    "[ClientService:OnUpdateGamePlayPhase:3473] OnUpdateGamePlayPhase : PlayGame, 48.6 48.6"
)


def test_parse_line_detects_match_start():
    event = parse_line(GAME_START_LINE)
    assert event == LogEvent(
        type=LogEventType.MATCH_START,
        local_time=datetime(2026, 9, 19, 22, 15, 57, 595000),
    )


def test_parse_line_detects_match_end():
    event = parse_line(LOBBY_RETURN_LINE)
    assert event == LogEvent(
        type=LogEventType.MATCH_END,
        local_time=datetime(2026, 9, 19, 22, 25, 12, 137000),
    )


def test_parse_line_ignores_unrelated_lines():
    assert parse_line(UNRELATED_LINE) is None


def test_parse_line_ignores_garbage():
    assert parse_line("not a log line at all") is None


def test_extract_matches_pairs_start_and_end():
    lines = [UNRELATED_LINE, GAME_START_LINE, UNRELATED_LINE, LOBBY_RETURN_LINE]
    matches = extract_matches(lines, local_tz=KST)

    assert len(matches) == 1
    m = matches[0]
    assert m.start_utc == datetime(2026, 9, 19, 13, 15, 57, 595000, tzinfo=timezone.utc)
    assert m.end_utc == datetime(2026, 9, 19, 13, 25, 12, 137000, tzinfo=timezone.utc)


def test_extract_matches_handles_multiple_matches():
    lines = [
        GAME_START_LINE, LOBBY_RETURN_LINE,
        GAME_START_LINE, LOBBY_RETURN_LINE,
    ]
    matches = extract_matches(lines, local_tz=KST)
    assert len(matches) == 2


def test_extract_matches_unfinished_match_has_none_end():
    lines = [GAME_START_LINE]
    matches = extract_matches(lines, local_tz=KST)
    assert len(matches) == 1
    assert matches[0].end_utc is None


def test_extract_matches_ignores_end_without_start():
    lines = [LOBBY_RETURN_LINE, GAME_START_LINE, LOBBY_RETURN_LINE]
    matches = extract_matches(lines, local_tz=KST)
    assert len(matches) == 1


def test_extract_matches_empty_input():
    assert extract_matches([], local_tz=KST) == []


def test_match_boundary_is_frozen():
    import pytest

    boundary = MatchBoundary(start_utc=datetime.now(timezone.utc), end_utc=None)
    with pytest.raises(Exception):
        boundary.start_utc = datetime.now(timezone.utc)  # type: ignore[misc]


