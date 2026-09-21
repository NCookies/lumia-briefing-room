from datetime import datetime, timedelta, timezone

import pytest

from lumia_briefing_room.pipeline.playerlog import (
    LogEvent,
    LogEventType,
    MatchBoundary,
    extract_matches,
    parse_line,
    tail_follow,
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


def test_tail_follow_yields_existing_lines_from_start(tmp_path):
    path = tmp_path / "log.txt"
    path.write_text("a\nb\n", encoding="utf-8")

    gen = tail_follow(path, start_at_end=False, poll_interval_sec=0.01)

    assert next(gen) == "a\n"
    assert next(gen) == "b\n"


def test_tail_follow_picks_up_appended_lines(tmp_path):
    path = tmp_path / "log.txt"
    path.write_text("a\n", encoding="utf-8")

    gen = tail_follow(path, start_at_end=False, poll_interval_sec=0.01)
    assert next(gen) == "a\n"

    with open(path, "a", encoding="utf-8") as f:
        f.write("b\n")

    assert next(gen) == "b\n"


def test_tail_follow_start_at_end_skips_existing_content(tmp_path):
    path = tmp_path / "log.txt"
    path.write_text("old\n", encoding="utf-8")

    gen = tail_follow(path, start_at_end=True, poll_interval_sec=0.01)

    with open(path, "a", encoding="utf-8") as f:
        f.write("new\n")

    assert next(gen) == "new\n"


def test_tail_follow_stops_when_should_stop_becomes_true(tmp_path):
    path = tmp_path / "log.txt"
    path.write_text("", encoding="utf-8")

    calls = {"n": 0}

    def should_stop():
        calls["n"] += 1
        return calls["n"] > 2  # 몇 번의 유휴 폴링 후 멈춘다

    gen = tail_follow(
        path, start_at_end=False, poll_interval_sec=0.01, should_stop=should_stop
    )

    with pytest.raises(StopIteration):
        next(gen)


def test_tail_follow_yields_pending_lines_before_stopping(tmp_path):
    path = tmp_path / "log.txt"
    path.write_text("a\n", encoding="utf-8")

    gen = tail_follow(
        path, start_at_end=False, poll_interval_sec=0.01, should_stop=lambda: True
    )

    assert next(gen) == "a\n"
    with pytest.raises(StopIteration):
        next(gen)


def test_tail_follow_restarts_from_the_top_when_the_file_is_truncated_and_rewritten(tmp_path):
    path = tmp_path / "log.txt"
    path.write_text("old line one\nold line two\n", encoding="utf-8")
    gen = tail_follow(path, start_at_end=True, poll_interval_sec=0.01)

    path.write_text("new\n", encoding="utf-8")

    assert next(gen) == "new\n"


def test_tail_follow_follows_a_file_that_is_deleted_and_recreated(tmp_path):
    path = tmp_path / "log.txt"
    path.write_text("x" * 50 + "\n", encoding="utf-8")
    gen = tail_follow(path, start_at_end=True, poll_interval_sec=0.01)

    path.unlink()
    path.write_text("fresh\n" + "y" * 80 + "\n", encoding="utf-8")

    assert next(gen) == "fresh\n"


def test_tail_follow_survives_the_file_being_briefly_missing(tmp_path):
    path = tmp_path / "log.txt"
    path.write_text("a\n", encoding="utf-8")
    gen = tail_follow(path, start_at_end=False, poll_interval_sec=0.01, should_stop=lambda: False)
    assert next(gen) == "a\n"
    path.unlink()
    import threading

    threading.Timer(0.1, lambda: path.write_text("b\n", encoding="utf-8")).start()

    assert next(gen) == "b\n"


def test_tail_follow_never_holds_the_file_open_between_polls(tmp_path):
    path = tmp_path / "log.txt"
    path.write_text("a\n", encoding="utf-8")
    gen = tail_follow(path, start_at_end=False, poll_interval_sec=0.01)
    assert next(gen) == "a\n"

    path.rename(tmp_path / "moved.txt")
    path.write_text("b\n", encoding="utf-8")

    assert next(gen) == "b\n"


def test_tail_follow_waits_for_the_end_of_a_partly_written_line(tmp_path):
    path = tmp_path / "log.txt"
    path.write_text("half", encoding="utf-8")
    gen = tail_follow(path, start_at_end=False, poll_interval_sec=0.01)

    import threading

    threading.Timer(0.1, lambda: open(path, "a", encoding="utf-8").write(" done\n")).start()

    assert next(gen) == "half done\n"
