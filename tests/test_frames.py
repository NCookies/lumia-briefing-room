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


@requires_ffmpeg
def test_frames_are_produced_lazily_so_memory_stays_flat(tmp_path, make_synthetic_session):
    """세그먼트 수백 개(수 GB)를 한 번에 메모리에 올리지 않는다 — 제너레이터가 프레임을 하나씩 낸다."""
    import inspect

    session_dir = make_synthetic_session(tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=6)
    session = RecordingSession.load(session_dir)

    gen = extract_keyframe_frames(session, stream=0, segment_numbers=list(range(1, 7)), ffmpeg_path=FFMPEG_PATH)

    assert inspect.isgenerator(gen)
    first_segment, first_frame = next(gen)
    assert first_segment == 1 and first_frame.shape == (48, 64, 3)
    gen.close()


@requires_ffmpeg
def test_closing_early_stops_ffmpeg_and_leaves_no_temp_files(tmp_path, make_synthetic_session, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    session_dir = make_synthetic_session(tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=8)
    session = RecordingSession.load(session_dir)

    gen = extract_keyframe_frames(session, stream=0, segment_numbers=list(range(1, 9)), ffmpeg_path=FFMPEG_PATH)
    next(gen)
    gen.close()

    assert list((tmp_path / "tmp").iterdir()) == []


@requires_ffmpeg
def test_streamed_frames_match_the_merged_file_decode(tmp_path, make_synthetic_session):
    """스트리밍으로 바꿔도 같은 프레임이 나온다 — 이어붙인 파일을 직접 디코딩한 것과 비교한다."""
    import subprocess

    session_dir = make_synthetic_session(tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=5)
    session = RecordingSession.load(session_dir)
    merged = tmp_path / "merged.mp4"
    write_merged_segment_file(session, 0, [1, 2, 3, 4, 5], merged)
    raw = subprocess.run(
        [str(FFMPEG_PATH), "-hide_banner", "-v", "error", "-skip_frame", "nokey", "-i", str(merged),
         "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        capture_output=True, check=True,
    ).stdout
    expected = reshape_raw_frames(raw, width=64, height=48)

    got = [frame for _, frame in extract_keyframe_frames(
        session, stream=0, segment_numbers=[1, 2, 3, 4, 5], ffmpeg_path=FFMPEG_PATH)]

    assert len(got) == len(expected) == 5
    for a, b in zip(got, expected):
        assert np.array_equal(a, b)


@requires_ffmpeg
def test_a_broken_segment_raises_instead_of_silently_dropping_frames(tmp_path, make_synthetic_session):
    session_dir = make_synthetic_session(tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=5)
    (session_dir / "chunk-stream0-00003.m4s").write_bytes(b"\x00" * 64)
    session = RecordingSession.load(session_dir)

    with pytest.raises(RuntimeError):
        list(extract_keyframe_frames(session, stream=0, segment_numbers=[1, 2, 3, 4, 5], ffmpeg_path=FFMPEG_PATH))
