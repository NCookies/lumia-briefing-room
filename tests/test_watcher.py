from datetime import datetime, timedelta, timezone
from pathlib import Path

from lumia_briefing_room.pipeline.playerlog import MatchBoundary
from lumia_briefing_room.video.segments import SegmentRange
from lumia_briefing_room.video.session import RecordingSession
from lumia_briefing_room.config import Config, WatchConfig
from lumia_briefing_room.pipeline.watcher import (
    ProcessedState,
    discover_backlog,
    find_session_for_time,
    match_key,
    remaining_margin_minutes,
    rescue_copy,
    resolve_buffer_minutes,
    run_forever,
    run_once,
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


def _write_chunk(session_dir: Path, stream: int, n: int, content: bytes = b"x") -> None:
    (session_dir / f"chunk-stream{stream}-{n:05d}.m4s").write_bytes(content)


def test_rescue_copy_copies_mpd_init_and_requested_segments(tmp_path):
    src = _make_session_dir(tmp_path, 1049590, datetime(2026, 1, 1, tzinfo=UTC))
    (src / "init-stream0.m4s").write_bytes(b"init0")
    (src / "init-stream1.m4s").write_bytes(b"init1")
    for n in (10, 11, 12):
        _write_chunk(src, 0, n, f"v{n}".encode())
        _write_chunk(src, 1, n, f"a{n}".encode())
    session = RecordingSession.load(src)

    dest = rescue_copy(session, SegmentRange(first=10, last=12), tmp_path / "rescue_root")

    assert (dest / "session.mpd").exists()
    assert (dest / "init-stream0.m4s").read_bytes() == b"init0"
    assert (dest / "init-stream1.m4s").read_bytes() == b"init1"
    for n in (10, 11, 12):
        assert (dest / f"chunk-stream0-{n:05d}.m4s").read_bytes() == f"v{n}".encode()
        assert (dest / f"chunk-stream1-{n:05d}.m4s").read_bytes() == f"a{n}".encode()


def test_rescue_copy_skips_missing_segments(tmp_path):
    src = _make_session_dir(tmp_path, 1049590, datetime(2026, 1, 1, tzinfo=UTC))
    (src / "init-stream0.m4s").write_bytes(b"init0")
    _write_chunk(src, 0, 10)
    # 11번은 없음 - 링버퍼가 이미 지웠다고 가정
    _write_chunk(src, 0, 12)
    session = RecordingSession.load(src)

    dest = rescue_copy(session, SegmentRange(first=10, last=12), tmp_path / "rescue_root")

    assert (dest / "chunk-stream0-00010.m4s").exists()
    assert not (dest / "chunk-stream0-00011.m4s").exists()
    assert (dest / "chunk-stream0-00012.m4s").exists()


def test_rescue_copy_result_is_loadable_as_a_session(tmp_path):
    src = _make_session_dir(tmp_path, 1049590, datetime(2026, 1, 1, tzinfo=UTC))
    (src / "init-stream0.m4s").write_bytes(b"init0")
    _write_chunk(src, 0, 10)
    session = RecordingSession.load(src)

    dest = rescue_copy(session, SegmentRange(first=10, last=10), tmp_path / "rescue_root")

    # 회귀: 목적지 폴더명이 원본과 같은 bg_<appid>_<날짜>_<시각> 패턴을 유지해야
    # RecordingSession.load() 가 폴더명에서 appid/시작시각을 다시 읽을 수 있다.
    assert dest.name == src.name
    reloaded = RecordingSession.load(dest)
    assert reloaded.width == session.width
    assert reloaded.start_utc == session.start_utc


def test_run_once_processes_unprocessed_matches_in_order(tmp_path):
    session_dir = _make_session_dir(tmp_path, 1049590, datetime(2026, 1, 1, tzinfo=UTC))
    m1 = MatchBoundary(
        start_utc=datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
        end_utc=datetime(2026, 1, 1, 0, 20, tzinfo=UTC),
    )
    m2 = MatchBoundary(
        start_utc=datetime(2026, 1, 1, 0, 30, tzinfo=UTC),
        end_utc=datetime(2026, 1, 1, 0, 45, tzinfo=UTC),
    )
    calls = []

    state = run_once(
        [m1, m2],
        ProcessedState(frozenset()),
        recording_root=tmp_path,
        now=lambda: datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
        rescue_threshold_min=20.0,
        buffer_minutes=120.0,
        process=lambda session_dir_, match, rescue: calls.append((session_dir_, match, rescue)),
        state_path=tmp_path / "state.json",
    )

    assert [c[1] for c in calls] == [m1, m2]
    assert state.processed_keys == {match_key(m1), match_key(m2)}
    assert ProcessedState.load(tmp_path / "state.json").processed_keys == state.processed_keys


def test_run_once_skips_already_processed():
    m1 = MatchBoundary(
        start_utc=datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
        end_utc=datetime(2026, 1, 1, 0, 20, tzinfo=UTC),
    )
    calls = []
    run_once(
        [m1],
        ProcessedState(frozenset({match_key(m1)})),
        recording_root=Path("."),
        now=lambda: datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
        rescue_threshold_min=20.0,
        buffer_minutes=120.0,
        process=lambda *a: calls.append(a),
        state_path=Path("/dev/null/unused"),
    )
    assert calls == []


def test_run_once_skips_when_session_not_found(tmp_path):
    m1 = MatchBoundary(
        start_utc=datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
        end_utc=datetime(2026, 1, 1, 0, 20, tzinfo=UTC),
    )
    calls = []
    state = run_once(
        [m1],
        ProcessedState(frozenset()),
        recording_root=tmp_path,  # 세션 폴더가 하나도 없음
        now=lambda: datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
        rescue_threshold_min=20.0,
        buffer_minutes=120.0,
        process=lambda *a: calls.append(a),
        state_path=tmp_path / "state.json",
    )
    assert calls == []
    assert state.processed_keys == frozenset()  # 처리 못 했으니 이력에도 안 남는다


def test_run_once_passes_rescue_flag_based_on_margin(tmp_path):
    session_dir = _make_session_dir(tmp_path, 1049590, datetime(2026, 1, 1, tzinfo=UTC))
    m1 = MatchBoundary(
        start_utc=datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
        end_utc=datetime(2026, 1, 1, 0, 20, tzinfo=UTC),
    )
    calls = []
    run_once(
        [m1],
        ProcessedState(frozenset()),
        recording_root=tmp_path,
        now=lambda: datetime(2026, 1, 1, 2, 3, tzinfo=UTC),  # margin = 120 - 118 = 2 <= 20
        rescue_threshold_min=20.0,
        buffer_minutes=120.0,
        process=lambda session_dir_, match, rescue: calls.append(rescue),
        state_path=tmp_path / "state.json",
    )
    assert calls == [True]


def test_run_forever_dispatches_match_on_end_event(tmp_path):
    session_dir = _make_session_dir(tmp_path, 1049590, datetime(2026, 9, 19, 13, 0, 0, tzinfo=UTC))
    lines = [GAME_START, LOBBY_RETURN]
    calls = []
    sleeps = []

    run_forever(
        lines,
        local_tz=KST,
        recording_root=tmp_path,
        now=lambda: datetime(2026, 9, 19, 13, 30, 0, tzinfo=UTC),
        delay_sec=5.0,
        rescue_threshold_min=20.0,
        buffer_minutes=120.0,
        process=lambda session_dir_, match, rescue: calls.append((session_dir_, match, rescue)),
        sleep=lambda s: sleeps.append(s),
    )

    assert len(calls) == 1
    assert calls[0][0] == session_dir
    assert sleeps == [5.0]


def test_run_forever_ignores_end_without_prior_start(tmp_path):
    calls = []
    run_forever(
        [LOBBY_RETURN],
        local_tz=KST,
        recording_root=tmp_path,
        now=lambda: datetime(2026, 9, 19, 13, 30, 0, tzinfo=UTC),
        delay_sec=5.0,
        rescue_threshold_min=20.0,
        buffer_minutes=120.0,
        process=lambda *a: calls.append(a),
        sleep=lambda s: None,
    )
    assert calls == []


def test_run_forever_handles_multiple_matches_in_stream(tmp_path):
    session_dir = _make_session_dir(tmp_path, 1049590, datetime(2026, 9, 19, 13, 0, 0, tzinfo=UTC))
    lines = [GAME_START, LOBBY_RETURN, GAME_START_2, LOBBY_RETURN_2]
    calls = []

    run_forever(
        lines,
        local_tz=KST,
        recording_root=tmp_path,
        now=lambda: datetime(2026, 9, 19, 14, 0, 0, tzinfo=UTC),
        delay_sec=0.0,
        rescue_threshold_min=20.0,
        buffer_minutes=120.0,
        process=lambda session_dir_, match, rescue: calls.append(match),
        sleep=lambda s: None,
    )

    assert len(calls) == 2


def test_run_forever_seeds_last_start_from_initial_param(tmp_path):
    session_dir = _make_session_dir(tmp_path, 1049590, datetime(2026, 9, 19, 13, 0, 0, tzinfo=UTC))
    initial_start = datetime(2026, 9, 19, 13, 5, 0, tzinfo=UTC)
    calls = []

    run_forever(
        [LOBBY_RETURN],
        local_tz=KST,
        recording_root=tmp_path,
        now=lambda: datetime(2026, 9, 19, 13, 30, 0, tzinfo=UTC),
        delay_sec=0.0,
        rescue_threshold_min=20.0,
        buffer_minutes=120.0,
        process=lambda session_dir_, match, rescue: calls.append(match),
        sleep=lambda s: None,
        initial_start_utc=initial_start,
    )

    assert len(calls) == 1
    assert calls[0].start_utc == initial_start


def test_resolve_buffer_minutes_uses_explicit_config_value(tmp_path):
    cfg = Config(watch=WatchConfig(buffer_minutes=90.0))
    assert resolve_buffer_minutes(cfg, tmp_path) == 90.0


def test_resolve_buffer_minutes_reads_from_dynamic_session(tmp_path):
    _make_session_dir(tmp_path, 1049590, datetime(2026, 1, 1, tzinfo=UTC))
    cfg = Config(watch=WatchConfig(buffer_minutes="auto"))
    assert resolve_buffer_minutes(cfg, tmp_path) == 120.0


def test_resolve_buffer_minutes_falls_back_to_default_when_no_session(tmp_path):
    cfg = Config(watch=WatchConfig(buffer_minutes="auto"))
    assert resolve_buffer_minutes(cfg, tmp_path) == 120.0


def test_resolve_buffer_minutes_falls_back_when_root_missing():
    cfg = Config(watch=WatchConfig(buffer_minutes="auto"))
    assert resolve_buffer_minutes(cfg, Path("/does/not/exist")) == 120.0
