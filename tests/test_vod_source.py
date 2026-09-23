import subprocess

import pytest

from lumia_briefing_room.video.source import FrameSource
from lumia_briefing_room.video.vod import VodFileSource, find_ffprobe, probe_video

FFMPEG_PATH = None
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
def vod_file(tmp_path):
    """10fps, 키프레임 1초 간격(-g 10), 8초짜리 64x48 영상."""
    path = tmp_path / "vod.mp4"
    subprocess.run(
        [
            str(FFMPEG_PATH), "-hide_banner", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10",
            "-t", "8", "-c:v", "libx264", "-g", "10", "-keyint_min", "10",
            "-sc_threshold", "0", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
    )
    return path


@requires_ffmpeg
def test_probe_video_reads_size_fps_and_duration(vod_file):
    info = probe_video(vod_file, ffprobe_path=FFPROBE_PATH)

    assert (info.width, info.height) == (64, 48)
    assert info.fps == pytest.approx(10.0)
    assert info.duration_sec == pytest.approx(8.0, abs=0.2)
    assert info.codec == "h264"


@requires_ffmpeg
def test_probe_video_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        probe_video(tmp_path / "없음.mp4", ffprobe_path=FFPROBE_PATH)


@requires_ffmpeg
def test_vod_source_yields_one_frame_per_keyframe_with_original_times(vod_file):
    src = VodFileSource(vod_file, ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)

    assert isinstance(src, FrameSource)
    assert (src.width, src.height) == (64, 48)
    frames = list(src.frames())

    assert [round(t) for t, _ in frames] == list(range(8))
    assert all(f.shape == (48, 64, 3) for _, f in frames)
    assert src.gaps() == []


@requires_ffmpeg
def test_vod_source_respects_start_and_end_window(vod_file):
    src = VodFileSource(
        vod_file, ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH,
        start_sec=3.5, end_sec=6.5,
    )

    assert [round(t) for t, _ in src.frames()] == [4, 5, 6]


@requires_ffmpeg
def test_vod_source_can_be_closed_early_without_hanging(vod_file):
    src = VodFileSource(vod_file, ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)

    gen = src.frames()
    t, _ = next(gen)
    gen.close()

    assert round(t) == 0


@requires_ffmpeg
def test_vod_source_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        VodFileSource(tmp_path / "없음.mp4", ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)


@requires_ffmpeg
def test_vod_source_raises_when_decoding_fails(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")

    with pytest.raises(Exception):
        list(VodFileSource(bad, ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH).frames())


def test_find_ffprobe_order_sibling_then_bundle_then_path(tmp_path, monkeypatch):
    from lumia_briefing_room.video.vod import find_ffprobe

    res = tmp_path / "res"
    (res / "vendor" / "ffmpeg").mkdir(parents=True)
    bundled = res / "vendor" / "ffmpeg" / "ffprobe.exe"
    bundled.write_bytes(b"")
    other = tmp_path / "other"
    other.mkdir()
    sibling = other / "ffprobe.exe"
    sibling.write_bytes(b"")
    monkeypatch.setenv("LUMIA_RESOURCE_DIR", str(res))
    monkeypatch.setattr("shutil.which", lambda name: "C:/path/ffprobe.exe")

    assert find_ffprobe(other / "ffmpeg.exe") == sibling
    sibling.unlink()
    assert find_ffprobe(other / "ffmpeg.exe") == bundled
    bundled.unlink()
    assert str(find_ffprobe(other / "ffmpeg.exe")).endswith("ffprobe.exe")
