import subprocess

import pytest

from lumia_briefing_room.video.frames import extract_tail_frames
from lumia_briefing_room.video.vod import find_ffprobe

try:
    from lumia_briefing_room.config import discover_ffmpeg

    FFMPEG_PATH = discover_ffmpeg()
except Exception:  # pragma: no cover
    FFMPEG_PATH = None

FFPROBE_PATH = find_ffprobe(FFMPEG_PATH) if FFMPEG_PATH else None
requires_ffmpeg = pytest.mark.skipif(
    FFMPEG_PATH is None or FFPROBE_PATH is None, reason="ffmpeg/ffprobe를 찾을 수 없다"
)


@pytest.fixture
def clip_10s(tmp_path):
    path = tmp_path / "v.mp4"
    subprocess.run(
        [
            str(FFMPEG_PATH), "-hide_banner", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10",
            "-t", "10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
    )
    return path


@requires_ffmpeg
def test_tail_frames_decodes_the_last_seconds_at_the_given_fps(clip_10s):
    frames = list(extract_tail_frames(clip_10s, tail_sec=3, fps=2, ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH))

    assert 5 <= len(frames) <= 7
    assert frames[0][1].shape == (48, 64, 3)
    assert [n for n, _ in frames] == list(range(len(frames)))


@requires_ffmpeg
def test_tail_frames_of_a_video_shorter_than_the_tail_returns_everything(clip_10s):
    frames = list(extract_tail_frames(clip_10s, tail_sec=60, fps=1, ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH))

    assert 9 <= len(frames) <= 11


@requires_ffmpeg
def test_tail_frames_stops_ffmpeg_when_the_consumer_closes_early(clip_10s):
    gen = extract_tail_frames(clip_10s, tail_sec=10, fps=10, ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)
    next(gen)
    gen.close()


@requires_ffmpeg
def test_tail_frames_without_tail_sec_reads_the_whole_file(clip_10s):
    frames = list(extract_tail_frames(clip_10s, tail_sec=None, fps=1, ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH))

    assert 9 <= len(frames) <= 11
