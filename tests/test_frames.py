import numpy as np
import pytest

from lumia_briefing_room.config import discover_ffmpeg
from lumia_briefing_room.profiles.models import Roi
from lumia_briefing_room.video.frames import (
    crop_roi,
    extract_keyframe_frames,
    reshape_raw_frames,
    write_merged_segment_file,
)
from lumia_briefing_room.video.session import RecordingSession

FFMPEG_PATH = discover_ffmpeg()
requires_ffmpeg = pytest.mark.skipif(FFMPEG_PATH is None, reason="ffmpeg를 찾을 수 없다")


def test_reshape_raw_frames_splits_into_correct_count_and_shape():
    width, height = 4, 3
    frame_bytes = width * height * 3
    raw = bytes(range(256)) * (frame_bytes * 2 // 256 + 1)
    raw = raw[: frame_bytes * 2]

    frames = reshape_raw_frames(raw, width=width, height=height)

    assert frames.shape == (2, height, width, 3)


def test_reshape_raw_frames_rejects_size_not_multiple_of_frame():
    with pytest.raises(ValueError):
        reshape_raw_frames(b"\x00" * 10, width=4, height=3)


def test_crop_roi_extracts_correct_slice():
    frame = np.arange(5 * 5 * 3, dtype=np.uint8).reshape(5, 5, 3)
    roi = Roi(x0=1, y0=2, x1=3, y1=4)
    cropped = crop_roi(frame, roi)
    assert cropped.shape == (2, 2, 3)
    assert np.array_equal(cropped, frame[2:4, 1:3])


@requires_ffmpeg
def test_extract_keyframe_frames_returns_one_frame_per_segment(tmp_path, make_synthetic_session):
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=5
    )
    session = RecordingSession.load(session_dir)

    results = list(
        extract_keyframe_frames(
            session, stream=0, segment_numbers=[1, 2, 3, 4, 5], ffmpeg_path=FFMPEG_PATH
        )
    )

    assert [seg for seg, _ in results] == [1, 2, 3, 4, 5]
    for _, frame in results:
        assert frame.shape == (48, 64, 3)


@requires_ffmpeg
def test_extract_keyframe_frames_can_crop_roi(tmp_path, make_synthetic_session):
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=3
    )
    session = RecordingSession.load(session_dir)

    roi = Roi(x0=10, y0=10, x1=30, y1=30)
    results = list(
        extract_keyframe_frames(
            session, stream=0, segment_numbers=[1, 2, 3], ffmpeg_path=FFMPEG_PATH
        )
    )
    crops = [crop_roi(frame, roi) for _, frame in results]
    assert all(c.shape == (20, 20, 3) for c in crops)


@requires_ffmpeg
def test_write_merged_segment_file_produces_playable_mp4(tmp_path, make_synthetic_session):
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=5
    )
    session = RecordingSession.load(session_dir)
    out_path = tmp_path / "merged.mp4"

    used = write_merged_segment_file(session, 0, [1, 2, 3, 4, 5], out_path)

    assert used == [1, 2, 3, 4, 5]
    assert out_path.exists() and out_path.stat().st_size > 0


@requires_ffmpeg
def test_write_merged_segment_file_uses_largest_contiguous_run(tmp_path, make_synthetic_session):
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=6
    )
    (session_dir / "chunk-stream0-00002.m4s").unlink()
    session = RecordingSession.load(session_dir)
    out_path = tmp_path / "merged.mp4"

    used = write_merged_segment_file(session, 0, [1, 2, 3, 4, 5, 6], out_path)

    assert used == [3, 4, 5, 6]


def test_write_merged_segment_file_returns_empty_when_nothing_exists(tmp_path):
    class _FakeSession:
        directory = tmp_path

    used = write_merged_segment_file(_FakeSession(), 0, [1, 2, 3], tmp_path / "out.mp4")
    assert used == []


@requires_ffmpeg
def test_extract_keyframe_frames_skips_missing_segments(tmp_path, make_synthetic_session):
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=5
    )
    (session_dir / "chunk-stream0-00003.m4s").unlink()
    session = RecordingSession.load(session_dir)

    results = list(
        extract_keyframe_frames(
            session, stream=0, segment_numbers=[1, 2, 3, 4, 5], ffmpeg_path=FFMPEG_PATH
        )
    )

    assert [seg for seg, _ in results] == [1, 2, 4, 5]
