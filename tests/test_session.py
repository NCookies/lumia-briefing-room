from datetime import datetime, timezone

import pytest

from lumia_briefing_room.video.session import RecordingSession, SessionParseError

DYNAMIC_MPD = """<?xml version="1.0" encoding="utf-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"
     type="dynamic"
     availabilityStartTime="2026-09-19T13:07:47Z"
     timeShiftBufferDepth="PT2H0M0.0S"
     maxSegmentDuration="PT3.0S">
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

STATIC_MPD = """<?xml version="1.0" encoding="utf-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"
     type="static"
     mediaPresentationDuration="PT12M47.43S"
     maxSegmentDuration="PT3.0S">
    <Period id="0" start="PT3H16M6.0S">
        <AdaptationSet id="0" contentType="video" maxWidth="2560" maxHeight="1440">
            <Representation id="0" mimeType="video/mp4" width="2560" height="1440">
                <SegmentTemplate timescale="1000000" duration="3000000"
                                 initialization="init-stream$RepresentationID$.m4s"
                                 media="chunk-stream$RepresentationID$-$Number%05d$.m4s"
                                 startNumber="3923"/>
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>"""


def _make_session_dir(tmp_path, folder_name, mpd_text):
    session_dir = tmp_path / folder_name
    session_dir.mkdir()
    (session_dir / "session.mpd").write_text(mpd_text, encoding="utf-8")
    return session_dir


def test_dynamic_session_reads_availability_start_time(tmp_path):
    d = _make_session_dir(tmp_path, "bg_1049590_20260919_130747", DYNAMIC_MPD)
    session = RecordingSession.load(d)
    assert session.start_utc == datetime(2026, 9, 19, 13, 7, 47, tzinfo=timezone.utc)
    assert session.width == 2560
    assert session.height == 1440
    assert session.segment_duration_sec == pytest.approx(3.0)
    assert session.buffer_minutes == pytest.approx(120.0)


def test_static_session_falls_back_to_folder_name(tmp_path):
    d = _make_session_dir(tmp_path, "bg_1049590_20260919_050108", STATIC_MPD)
    session = RecordingSession.load(d)
    assert session.start_utc == datetime(2026, 9, 19, 5, 1, 8, tzinfo=timezone.utc)
    assert session.width == 2560
    assert session.height == 1440


def test_static_session_has_no_measured_buffer_minutes(tmp_path):
    d = _make_session_dir(tmp_path, "bg_1049590_20260919_050108", STATIC_MPD)
    session = RecordingSession.load(d)
    assert session.buffer_minutes is None


def test_missing_mpd_raises(tmp_path):
    d = tmp_path / "bg_1049590_20260919_130747"
    d.mkdir()
    with pytest.raises(SessionParseError):
        RecordingSession.load(d)


def test_folder_name_without_valid_pattern_raises(tmp_path):
    d = tmp_path / "not-a-session-folder"
    d.mkdir()
    (d / "session.mpd").write_text(STATIC_MPD, encoding="utf-8")
    with pytest.raises(SessionParseError):
        RecordingSession.load(d)


def test_appid_extracted_from_folder_name(tmp_path):
    d = _make_session_dir(tmp_path, "bg_1049590_20260919_130747", DYNAMIC_MPD)
    session = RecordingSession.load(d)
    assert session.app_id == 1049590
