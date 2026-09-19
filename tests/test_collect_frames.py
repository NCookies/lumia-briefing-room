import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from collect_frames import collect  # noqa: E402

from lumia_briefing_room.config import discover_ffmpeg
from lumia_briefing_room.video.session import RecordingSession

FFMPEG_PATH = discover_ffmpeg()
requires_ffmpeg = pytest.mark.skipif(FFMPEG_PATH is None, reason="ffmpeg 를 찾을 수 없다")


@requires_ffmpeg
def test_collect_saves_one_png_per_segment(tmp_path, make_synthetic_session):
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=5
    )
    session = RecordingSession.load(session_dir)
    out_dir = tmp_path / "frames"

    saved = collect(session, 1, 5, 1, out_dir, ffmpeg_path=FFMPEG_PATH)

    assert saved == [1, 2, 3, 4, 5]
    for n in saved:
        assert (out_dir / f"seg_{n:05d}.png").exists()


@requires_ffmpeg
def test_collect_respects_step(tmp_path, make_synthetic_session):
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=5
    )
    session = RecordingSession.load(session_dir)
    out_dir = tmp_path / "frames"

    saved = collect(session, 1, 5, 2, out_dir, ffmpeg_path=FFMPEG_PATH)

    assert saved == [1, 3, 5]


@requires_ffmpeg
def test_collect_skips_missing_segments(tmp_path, make_synthetic_session):
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=5
    )
    (session_dir / "chunk-stream0-00003.m4s").unlink()
    session = RecordingSession.load(session_dir)
    out_dir = tmp_path / "frames"

    saved = collect(session, 1, 5, 1, out_dir, ffmpeg_path=FFMPEG_PATH)

    assert saved == [1, 2, 4, 5]
    assert not (out_dir / "seg_00003.png").exists()
