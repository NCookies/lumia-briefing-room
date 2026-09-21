import numpy as np
import pytest

from lumia_briefing_room.detect.match import detect_match, detect_source
from lumia_briefing_room.video.segments import SegmentRange
from lumia_briefing_room.video.session import RecordingSession
from lumia_briefing_room.video.source import FrameSource, SteamSegmentSource

FFMPEG_PATH = None
try:
    from lumia_briefing_room.config import discover_ffmpeg

    FFMPEG_PATH = discover_ffmpeg()
except Exception:  # pragma: no cover
    FFMPEG_PATH = None

requires_ffmpeg = pytest.mark.skipif(FFMPEG_PATH is None, reason="ffmpeg를 찾을 수 없다")


class ListSource:
    def __init__(self, width, height, frames, gaps=()):
        self.width = width
        self.height = height
        self._frames = frames
        self._gaps = list(gaps)

    def frames(self):
        yield from self._frames

    def gaps(self):
        return list(self._gaps)


def test_list_source_satisfies_protocol():
    src = ListSource(64, 48, [])
    assert isinstance(src, FrameSource)


def test_detect_source_analyzes_frames_at_source_times_and_keeps_gaps():
    black = np.zeros((1440, 2560, 3), dtype=np.uint8)
    src = ListSource(2560, 1440, [(0.0, black), (1.0, black), (2.0, black)], gaps=[(5.0, 9.0)])

    result = detect_source(src)

    assert result.gaps == [(5.0, 9.0)]
    assert result.source_incomplete is True
    assert result.intervals == []


def test_detect_source_no_gaps_is_complete():
    black = np.zeros((1440, 2560, 3), dtype=np.uint8)
    src = ListSource(2560, 1440, [(0.0, black), (1.0, black)])

    assert detect_source(src).source_incomplete is False


@requires_ffmpeg
def test_steam_segment_source_yields_segment_start_times_and_gaps(tmp_path, make_synthetic_session):
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=6
    )
    (session_dir / "chunk-stream0-00004.m4s").unlink()
    session = RecordingSession.load(session_dir)

    src = SteamSegmentSource(
        session, SegmentRange(first=1, last=6), stream=0, ffmpeg_path=FFMPEG_PATH
    )

    assert (src.width, src.height) == (64, 48)
    assert src.gaps() == [(3.0, 4.0)]
    times = [t for t, _ in src.frames()]
    assert times == [0.0, 1.0, 2.0, 4.0, 5.0]


@requires_ffmpeg
def test_detect_match_equals_detect_source_over_steam_source(tmp_path, make_synthetic_session):
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=6
    )
    (session_dir / "chunk-stream0-00004.m4s").unlink()
    session = RecordingSession.load(session_dir)
    seg_range = SegmentRange(first=1, last=6)

    via_match = detect_match(session, seg_range, ffmpeg_path=FFMPEG_PATH)
    via_source = detect_source(
        SteamSegmentSource(session, seg_range, stream=0, ffmpeg_path=FFMPEG_PATH)
    )

    assert via_match == via_source
