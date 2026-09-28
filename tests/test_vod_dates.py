from datetime import datetime

from lumia_briefing_room.pipeline.vod_dates import (
    date_from_creation_time,
    date_from_mtime,
    is_valid_iso_date,
    resolve_video_date,
)


def test_date_from_creation_time_reads_z_suffixed_utc_timestamp():
    assert date_from_creation_time("2026-09-27T10:00:00.000000Z") is not None


def test_date_from_creation_time_none_when_missing():
    assert date_from_creation_time(None) is None
    assert date_from_creation_time("") is None


def test_date_from_creation_time_none_when_unparsable():
    assert date_from_creation_time("not-a-date") is None


def test_date_from_mtime_uses_local_date():
    mtime = datetime(2026, 9, 27, 15, 30).timestamp()
    assert date_from_mtime(mtime) == "2026-09-27"


def test_resolve_video_date_prefers_user_override():
    result = resolve_video_date(
        override="2026-01-01", creation_time="2026-09-27T10:00:00Z", mtime=datetime(2026, 9, 28).timestamp()
    )
    assert result == "2026-01-01"


def test_resolve_video_date_falls_back_to_creation_time_when_no_override():
    result = resolve_video_date(
        override=None, creation_time="2026-09-27T10:00:00Z", mtime=datetime(2026, 9, 28).timestamp()
    )
    assert result == date_from_creation_time("2026-09-27T10:00:00Z")


def test_resolve_video_date_falls_back_to_mtime_when_no_creation_time():
    mtime = datetime(2026, 9, 28, 12, 0).timestamp()
    result = resolve_video_date(override=None, creation_time=None, mtime=mtime)
    assert result == "2026-09-28"


def test_resolve_video_date_falls_back_to_mtime_when_creation_time_unparsable():
    mtime = datetime(2026, 9, 28, 12, 0).timestamp()
    result = resolve_video_date(override=None, creation_time="garbage", mtime=mtime)
    assert result == "2026-09-28"


def test_resolve_video_date_none_when_nothing_available():
    assert resolve_video_date(override=None, creation_time=None, mtime=None) is None


def test_resolve_video_date_ignores_blank_override():
    mtime = datetime(2026, 9, 28, 12, 0).timestamp()
    result = resolve_video_date(override="  ", creation_time=None, mtime=mtime)
    assert result == "2026-09-28"


def test_is_valid_iso_date():
    assert is_valid_iso_date("2026-09-27") is True
    assert is_valid_iso_date("2026-9-27") is False
    assert is_valid_iso_date("2026-13-40") is False
    assert is_valid_iso_date("") is False
    assert is_valid_iso_date("not-a-date") is False
