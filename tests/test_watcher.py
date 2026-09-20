from datetime import datetime, timedelta, timezone

from lumia_briefing_room.pipeline.playerlog import MatchBoundary
from lumia_briefing_room.pipeline.watcher import (
    ProcessedState,
    discover_backlog,
    find_session_for_time,
    match_key,
    remaining_margin_minutes,
    should_rescue,
    unprocessed_matches,
)

KST = timezone(timedelta(hours=9))
UTC = timezone.utc


def test_remaining_margin_normal_operation():
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    now = start + timedelta(minutes=20)  # 매치 길이 20분, 방금 끝남
    margin = remaining_margin_minutes(start, now, buffer_minutes=120)
    assert margin == 100.0


def test_remaining_margin_app_was_off_for_a_while():
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    now = start + timedelta(minutes=110)  # 매치 20분 + 앱 꺼짐 90분
    margin = remaining_margin_minutes(start, now, buffer_minutes=120)
    assert margin == 10.0


def test_remaining_margin_can_go_negative_when_lost():
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    now = start + timedelta(minutes=150)
    margin = remaining_margin_minutes(start, now, buffer_minutes=120)
    assert margin == -30.0


def test_should_rescue_below_threshold():
    assert should_rescue(15.0, threshold_min=20.0) is True


def test_should_rescue_above_threshold():
    assert should_rescue(100.0, threshold_min=20.0) is False


def test_should_rescue_exactly_at_threshold():
    assert should_rescue(20.0, threshold_min=20.0) is True


def _boundary(start_min, end_min=None):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return MatchBoundary(
        start_utc=base + timedelta(minutes=start_min),
        end_utc=base + timedelta(minutes=end_min) if end_min is not None else None,
    )


def test_match_key_is_stable_iso_string():
    m = _boundary(0, 20)
    assert match_key(m) == m.start_utc.isoformat()


def test_unprocessed_matches_filters_seen_and_unfinished():
    finished_seen = _boundary(0, 20)
    finished_unseen = _boundary(30, 50)
    unfinished = _boundary(60)

    state = ProcessedState(frozenset({match_key(finished_seen)}))
    result = unprocessed_matches([finished_seen, finished_unseen, unfinished], state)

    assert result == [finished_unseen]


def test_processed_state_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    state = ProcessedState(frozenset({"a", "b"}))
    state.save(path)

    loaded = ProcessedState.load(path)
    assert loaded.processed_keys == {"a", "b"}


def test_processed_state_load_missing_file_is_empty(tmp_path):
    state = ProcessedState.load(tmp_path / "does_not_exist.json")
    assert state.processed_keys == frozenset()


def test_processed_state_with_added_is_immutable():
    state = ProcessedState(frozenset({"a"}))
    new_state = state.with_added("b")
    assert state.processed_keys == {"a"}
    assert new_state.processed_keys == {"a", "b"}


GAME_START = (
    "[INFO][H][2026-09-19 22:15:57,595][1][LoadingView:Show:194] "
    "[PROFILE TIME][LOADING][GAME]"
)
LOBBY_RETURN = (
    "[INFO][H][2026-09-19 22:25:12,137][1][LoadingView:Show:135] "
    "[PROFILE TIME][LOADING][LOBBY]"
)
GAME_START_2 = (
    "[INFO][H][2026-09-19 23:00:00,000][1][LoadingView:Show:194] "
    "[PROFILE TIME][LOADING][GAME]"
)
LOBBY_RETURN_2 = (
    "[INFO][H][2026-09-19 23:10:00,000][1][LoadingView:Show:135] "
    "[PROFILE TIME][LOADING][LOBBY]"
)


def test_discover_backlog_reads_prev_then_current(tmp_path):
    prev = tmp_path / "Player-prev.log"
    prev.write_text(GAME_START + "\n" + LOBBY_RETURN + "\n", encoding="utf-8")
    current = tmp_path / "Player.log"
    current.write_text(GAME_START_2 + "\n" + LOBBY_RETURN_2 + "\n", encoding="utf-8")

    matches = discover_backlog(current, prev, local_tz=KST)

    assert len(matches) == 2
    assert matches[0].start_utc < matches[1].start_utc


def test_discover_backlog_without_prev_file(tmp_path):
    current = tmp_path / "Player.log"
    current.write_text(GAME_START + "\n" + LOBBY_RETURN + "\n", encoding="utf-8")

    matches = discover_backlog(current, None, local_tz=KST)
    assert len(matches) == 1


def test_discover_backlog_missing_current_file(tmp_path):
    matches = discover_backlog(tmp_path / "missing.log", None, local_tz=KST)
    assert matches == []


DYNAMIC_MPD = """<?xml version="1.0" encoding="utf-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="dynamic"
     availabilityStartTime="{start}"
     timeShiftBufferDepth="PT2H0M0.0S" maxSegmentDuration="PT3.0S">
    <Period id="0" start="PT0.0S">
        <AdaptationSet id="0" contentType="video" maxWidth="2560" maxHeight="1440">
            <Representation id="0" mimeType="video/mp4" width="2560" height="1440">
                <SegmentTemplate timescale="1000000" duration="3000000"
                                 initialization="init-stream$RepresentationID$.m4s"
                                 media="chunk-stream$RepresentationID$-$Number%05d$.m4s"
                                 startNumber="1"/>
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>"""


def _make_session_dir(root, app_id, start_utc):
    name = f"bg_{app_id}_{start_utc:%Y%m%d}_{start_utc:%H%M%S}"
    d = root / name
    d.mkdir()
    (d / "session.mpd").write_text(
        DYNAMIC_MPD.format(start=start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")), encoding="utf-8"
    )
    return d


def test_find_session_for_time_picks_latest_started_covering_session(tmp_path):
    t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    _make_session_dir(tmp_path, 1049590, t0)
    newer = _make_session_dir(tmp_path, 1049590, t1)

    target = t1 + timedelta(minutes=30)
    found = find_session_for_time(tmp_path, target)

    assert found == newer


def test_find_session_for_time_ignores_sessions_starting_after_target(tmp_path):
    t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    older = _make_session_dir(tmp_path, 1049590, t0)
    _make_session_dir(tmp_path, 1049590, t1)

    target = t0 + timedelta(minutes=30)
    found = find_session_for_time(tmp_path, target)

    assert found == older


def test_find_session_for_time_returns_none_when_nothing_matches(tmp_path):
    t1 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    _make_session_dir(tmp_path, 1049590, t1)

    found = find_session_for_time(tmp_path, t1 - timedelta(hours=1))
    assert found is None


def test_find_session_for_time_empty_directory(tmp_path):
    assert find_session_for_time(tmp_path, datetime.now(tz=UTC)) is None


def test_find_session_for_time_ignores_non_session_directories(tmp_path):
    (tmp_path / "not_a_session").mkdir()
    (tmp_path / "clips").mkdir()
    assert find_session_for_time(tmp_path, datetime.now(tz=UTC)) is None
