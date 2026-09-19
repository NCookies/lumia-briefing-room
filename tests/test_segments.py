from datetime import datetime, timedelta, timezone

import pytest

from lumia_briefing_room.video.segments import (
    SegmentRange,
    existing_segment_numbers,
    segment_number_at,
    segment_time_range,
)


def _make_session(**overrides):
    from lumia_briefing_room.video.session import RecordingSession

    defaults = dict(
        directory=None,
        app_id=1049590,
        start_utc=datetime(2026, 9, 19, 13, 7, 47, tzinfo=timezone.utc),
        width=2560,
        height=1440,
        segment_duration_sec=3.0,
        buffer_minutes=120.0,
    )
    defaults.update(overrides)
    return RecordingSession(**defaults)


def test_segment_number_at_session_start_is_one():
    session = _make_session()
    assert segment_number_at(session, session.start_utc) == 1


def test_segment_number_at_matches_research_example():
    # research.md: 2100번 조각 -> start_time 6297.002454s -> (2100-1)*3 = 6297
    session = _make_session()
    t = session.start_utc + timedelta(seconds=6297.5)
    assert segment_number_at(session, t) == 2100


def test_segment_time_range_returns_start_and_end_offset():
    session = _make_session()
    t0 = session.start_utc + timedelta(seconds=100)
    t1 = session.start_utc + timedelta(seconds=110)
    seg_range = segment_time_range(session, t0, t1)
    assert isinstance(seg_range, SegmentRange)
    # 100s -> seg 34 (99..102), 110s -> seg 37 (108..111)
    assert seg_range.first == 34
    assert seg_range.last == 37


def test_segment_time_range_rejects_end_before_start():
    session = _make_session()
    t0 = session.start_utc + timedelta(seconds=200)
    t1 = session.start_utc + timedelta(seconds=100)
    with pytest.raises(ValueError):
        segment_time_range(session, t0, t1)


def test_existing_segment_numbers_filters_missing_and_tmp(tmp_path):
    session = _make_session(directory=tmp_path)
    (tmp_path / "init-stream0.m4s").write_bytes(b"")
    for n in (10, 11, 13):
        (tmp_path / f"chunk-stream0-{n:05d}.m4s").write_bytes(b"")
    (tmp_path / "chunk-stream0-00012.m4s.tmp").write_bytes(b"")

    existing = existing_segment_numbers(session, stream=0, first=10, last=13)
    assert existing == [10, 11, 13]


def test_existing_segment_numbers_empty_range(tmp_path):
    session = _make_session(directory=tmp_path)
    existing = existing_segment_numbers(session, stream=0, first=1, last=5)
    assert existing == []


def test_segment_range_gaps_detects_missing_numbers():
    seg_range = SegmentRange(first=10, last=15)
    gaps = seg_range.gaps(existing=[10, 11, 13, 14, 15])
    assert gaps == [(12, 12)]


def test_segment_range_gaps_merges_consecutive_missing():
    seg_range = SegmentRange(first=10, last=15)
    gaps = seg_range.gaps(existing=[10, 15])
    assert gaps == [(11, 14)]


def test_segment_range_gaps_no_gap_when_all_present():
    seg_range = SegmentRange(first=10, last=12)
    gaps = seg_range.gaps(existing=[10, 11, 12])
    assert gaps == []
