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




def _line(ts: str, body: str, cls: str = "ChannelServerService:OnReceiveMatchingUpdate:555") -> str:
    return f"[INFO][DESKTOP-IFDC4S7][2026-09-30 {ts}][1][{cls}] {body}"


def _start_matching(ts):
    return _line(ts, "[OnReceiveMatchingUpdate] matchingNotification : StartMatching")


def _matching_complete(ts):
    return _line(ts, "[OnReceiveMatchingUpdate] MatchingComplete, matchPadding.userCount : 66",
                 "ChannelServerService:OnReceiveMatchingUpdate:552")


def _loading_game(ts):
    return _line(ts, "[PROFILE TIME][LOADING][GAME]", "LoadingView:Show:194")


def _loading_lobby(ts):
    return _line(ts, "[PROFILE TIME][LOADING][LOBBY]", "LoadingView:Show:135")


def _set_mode(ts, mode):
    return _line(ts, f"Invoked: {mode}", "GlobalUserData:SetMatchingMode:142")


def _utc(hh, mm, ss):
    return datetime(2026, 9, 29, hh, mm, ss, tzinfo=timezone.utc)


def test_match_starts_at_last_matching_complete_before_loading():
    lines = [
        _start_matching("00:22:55,000"),
        _matching_complete("00:24:00,931"),
        _loading_game("00:25:20,113"),
        _loading_lobby("00:46:41,487"),
    ]
    (m,) = extract_matches(lines, local_tz=KST)
    assert m.start_utc == datetime(2026, 9, 29, 15, 24, 0, 931000, tzinfo=timezone.utc)
    assert m.loading_utc == datetime(2026, 9, 29, 15, 25, 20, 113000, tzinfo=timezone.utc)
    assert m.end_utc == datetime(2026, 9, 29, 15, 46, 41, 487000, tzinfo=timezone.utc)


def test_dodged_matching_complete_is_discarded_when_start_matching_follows():
    lines = [
        _start_matching("00:10:00,000"),
        _matching_complete("00:11:00,000"),
        _start_matching("00:12:00,000"),
        _matching_complete("00:13:00,000"),
        _loading_game("00:14:20,000"),
        _loading_lobby("00:30:00,000"),
    ]
    (m,) = extract_matches(lines, local_tz=KST)
    assert m.start_utc == datetime(2026, 9, 29, 15, 13, 0, tzinfo=timezone.utc)


def test_last_matching_complete_wins_without_start_matching_between():
    lines = [
        _matching_complete("00:11:00,000"),
        _matching_complete("00:13:00,000"),
        _loading_game("00:14:20,000"),
        _loading_lobby("00:30:00,000"),
    ]
    (m,) = extract_matches(lines, local_tz=KST)
    assert m.start_utc == datetime(2026, 9, 29, 15, 13, 0, tzinfo=timezone.utc)


def test_without_matching_complete_loading_is_the_start():
    lines = [_loading_game("00:14:20,000"), _loading_lobby("00:30:00,000")]
    (m,) = extract_matches(lines, local_tz=KST)
    assert m.start_utc == m.loading_utc == datetime(2026, 9, 29, 15, 14, 20, tzinfo=timezone.utc)


def test_matching_complete_does_not_leak_into_next_game():
    lines = [
        _matching_complete("00:11:00,000"),
        _loading_game("00:12:20,000"),
        _loading_lobby("00:30:00,000"),
        _loading_game("00:40:00,000"),
        _loading_lobby("00:50:00,000"),
    ]
    first, second = extract_matches(lines, local_tz=KST)
    assert first.start_utc == datetime(2026, 9, 29, 15, 11, 0, tzinfo=timezone.utc)
    assert second.start_utc == second.loading_utc


def test_stale_matching_complete_far_before_loading_is_ignored():
    lines = [
        _matching_complete("00:00:00,000"),
        _loading_game("00:40:00,000"),
        _loading_lobby("00:50:00,000"),
    ]
    (m,) = extract_matches(lines, local_tz=KST)
    assert m.start_utc == m.loading_utc


def test_practice_mode_by_set_matching_mode_is_not_a_game():
    lines = [
        _set_mode("00:16:39,856", "Normal"),
        _set_mode("00:16:54,636", "Practice"),
        _loading_game("00:17:11,200"),
        _loading_lobby("00:20:35,923"),
        _set_mode("00:20:45,905", "Normal"),
        _matching_complete("00:24:00,931"),
        _loading_game("00:25:20,113"),
        _loading_lobby("00:46:41,487"),
    ]
    (m,) = extract_matches(lines, local_tz=KST)
    assert m.start_utc == datetime(2026, 9, 29, 15, 24, 0, 931000, tzinfo=timezone.utc)


def test_practice_mode_by_battle_game_info_inside_the_game_is_not_a_game():
    info = '\tbattleGameInfo: {"gameId":0,"gameKind":"Default","matchingMode":"Practice","matchingTeamMode":"Squad"}'
    lines = [_loading_game("00:17:11,200"), info, _loading_lobby("00:20:35,923")]
    assert extract_matches(lines, local_tz=KST) == []


def test_practice_mode_does_not_carry_over_to_custom_game():
    lines = [
        _set_mode("00:16:54,636", "Practice"),
        _loading_game("00:17:11,200"),
        _loading_lobby("00:20:35,923"),
        _loading_game("00:30:00,000"),
        _loading_lobby("00:40:00,000"),
    ]
    (m,) = extract_matches(lines, local_tz=KST)
    assert m.loading_utc == datetime(2026, 9, 29, 15, 30, 0, tzinfo=timezone.utc)


def test_unfinished_game_keeps_widened_start():
    lines = [_matching_complete("00:24:00,931"), _loading_game("00:25:20,113")]
    (m,) = extract_matches(lines, local_tz=KST)
    assert m.end_utc is None
    assert m.start_utc == datetime(2026, 9, 29, 15, 24, 0, 931000, tzinfo=timezone.utc)
