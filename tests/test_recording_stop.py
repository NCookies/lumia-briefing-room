from datetime import datetime, timezone

from lumia_briefing_room.pipeline import recording_stop as rs
from lumia_briefing_room.video.segments import SegmentRange


class Session:
    def __init__(self, directory):
        self.directory = directory


def _session(tmp_path, last: int | None):
    d = tmp_path / "bg_1049590_20260930_151337"
    d.mkdir(parents=True)
    if last is not None:
        for n in range(max(1, last - 3), last + 1):
            (d / f"chunk-stream0-{n:05d}.m4s").write_bytes(b"x")
            (d / f"chunk-stream1-{n:05d}.m4s").write_bytes(b"x")
    return Session(d)


def test_recording_that_ended_before_the_game_started(tmp_path):
    assert rs.recording_stop(_session(tmp_path, 384), SegmentRange(680, 1180)) == "before"


def test_empty_recording_counts_as_stopped_before(tmp_path):
    assert rs.recording_stop(_session(tmp_path, None), SegmentRange(680, 1180)) == "before"


def test_recording_that_ended_in_the_middle_of_the_game(tmp_path):
    assert rs.recording_stop(_session(tmp_path, 384), SegmentRange(383, 663)) == "during"


def test_recording_that_covers_the_game_up_to_a_few_unwritten_segments_is_fine(tmp_path):
    assert rs.recording_stop(_session(tmp_path, 365), SegmentRange(35, 365)) is None
    assert rs.recording_stop(_session(tmp_path / "b", 362), SegmentRange(35, 365)) is None


def _game(**kw):
    base = {
        "gameKey": "20260930_154736",
        "source": "steam",
        "sessionStartUtc": "2026-09-30T15:13:37Z",
        "matchStartUtc": "2026-09-30T15:47:36.594000Z",
        "matchEndUtc": "2026-09-30T16:12:36.249000Z",
        "fullVideo": None,
        "fullVideoError": None,
    }
    return {**base, **kw}


def test_record_written_with_the_flag_uses_it():
    game = _game(recordingStopped="before", fullVideoError=rs.STOPPED_BEFORE_MESSAGE)
    assert rs.stopped_of_record(game) == "before"
    assert rs.error_of_record(game) == rs.STOPPED_BEFORE_MESSAGE


def test_old_record_with_missing_segments_reads_as_stopped_before():
    game = _game(fullVideoError="세그먼트를 찾을 수 없다: 680-1180")
    assert rs.stopped_of_record(game) == "before"
    assert rs.error_of_record(game) == rs.STOPPED_BEFORE_MESSAGE


def test_old_record_with_a_full_video_that_ends_early_reads_as_stopped_during():
    game = _game(
        matchStartUtc="2026-09-30T15:32:47.406000Z",
        matchEndUtc="2026-09-30T15:46:44.922000Z",
        fullVideo={"segmentStart": 384, "segmentEnd": 384, "segmentDurationSec": 3.0},
    )
    assert rs.stopped_of_record(game) == "during"


def test_old_record_with_a_complete_full_video_is_not_flagged():
    game = _game(
        matchStartUtc="2026-09-30T15:15:21.657000Z",
        matchEndUtc="2026-09-30T15:31:51.064000Z",
        fullVideo={"segmentStart": 35, "segmentEnd": 365, "segmentDurationSec": 3.0},
    )
    assert rs.stopped_of_record(game) is None


def test_other_failures_and_other_sources_are_not_flagged():
    assert rs.stopped_of_record(_game(fullVideoError="저장 공간이 부족해 풀영상을 만들지 못했습니다")) is None
    assert rs.error_of_record(_game(fullVideoError="저장 공간이 부족")) == "저장 공간이 부족"
    assert rs.stopped_of_record(_game(source="vod", fullVideoError="세그먼트를 찾을 수 없다: 1-2")) is None
    assert rs.stopped_of_record(_game(fullVideo=None, fullVideoError=None, fullVideoDeletedAt="2026-10-01T00:00:00Z")) is None
