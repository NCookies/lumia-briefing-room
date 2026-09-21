import json
import re
import subprocess
from pathlib import Path

import pytest

from lumia_briefing_room.config import ThumbnailConfig
from lumia_briefing_room.pipeline.trim import trim_clip, validate_range

from conftest import FFMPEG_PATH, requires_ffmpeg


def make_video(path: Path, seconds: int = 20) -> None:
    subprocess.run(
        [
            str(FFMPEG_PATH), "-hide_banner", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=size=320x180:rate=30:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-c:v", "libx264", "-g", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )


def video_seconds(path: Path) -> float:
    """편집 리스트를 적용해 실제로 보이는 프레임 수로 잰다(OpenCV 프레임 수는 숨은 프리롤을 셈한다)."""
    out = subprocess.run(
        [str(FFMPEG_PATH), "-hide_banner", "-i", str(path), "-map", "0:v", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    frames = int(re.findall(r"frame=\s*(\d+)", out)[-1])
    return frames / 30.0


def write_clip(tmp_path: Path, seconds: int = 20, **meta) -> Path:
    mp4 = tmp_path / "clip1.mp4"
    make_video(mp4, seconds)
    thumb = tmp_path / ".thumbs" / "clip1.jpg"
    thumb.parent.mkdir()
    thumb.write_bytes(b"old thumbnail")
    data = {
        "title": "t", "durationSec": float(seconds), "videoOffsetSec": 100.0,
        "thumbnailPath": str(thumb), "userLabel": "pvp", **meta,
    }
    meta_path = tmp_path / "clip1.json"
    meta_path.write_text(json.dumps(data), encoding="utf-8")
    return meta_path


def test_validate_range_accepts_a_range_inside_the_clip():
    validate_range(2.0, 10.0, 20.0)
    validate_range(0.0, 20.0, 20.0)


@pytest.mark.parametrize(
    "start,end",
    [(-1.0, 5.0), (5.0, 5.0), (8.0, 4.0), (0.0, 25.0), (3.0, 3.5)],
)
def test_validate_range_rejects_bad_ranges(start, end):
    with pytest.raises(ValueError):
        validate_range(start, end, 20.0)


@requires_ffmpeg
def test_trim_keeps_only_the_selected_range_and_updates_metadata(tmp_path):
    meta_path = write_clip(tmp_path)

    meta = trim_clip(meta_path, 5.5, 12.5, ffmpeg_path=FFMPEG_PATH, thumbnail=ThumbnailConfig())

    assert video_seconds(tmp_path / "clip1.mp4") == pytest.approx(7.0, abs=0.2)
    assert meta["durationSec"] == pytest.approx(7.0)
    assert meta["videoOffsetSec"] == pytest.approx(105.5)
    assert meta["trimmed"] is True and meta["originalDurationSec"] == 20.0
    assert meta["userLabel"] == "pvp"
    assert json.loads(meta_path.read_text(encoding="utf-8")) == meta
    assert (tmp_path / ".thumbs" / "clip1.jpg").read_bytes() != b"old thumbnail"
    assert not list(tmp_path.glob("*.trim.mp4"))


@requires_ffmpeg
def test_trimming_twice_keeps_the_first_original_duration(tmp_path):
    meta_path = write_clip(tmp_path)

    trim_clip(meta_path, 2.0, 16.0, ffmpeg_path=FFMPEG_PATH, thumbnail=ThumbnailConfig())
    meta = trim_clip(meta_path, 3.0, 9.0, ffmpeg_path=FFMPEG_PATH, thumbnail=ThumbnailConfig())

    assert meta["originalDurationSec"] == 20.0
    assert meta["durationSec"] == pytest.approx(6.0)
    assert meta["videoOffsetSec"] == pytest.approx(105.0)
    assert video_seconds(tmp_path / "clip1.mp4") == pytest.approx(6.0, abs=0.2)


@requires_ffmpeg
def test_failed_trim_leaves_the_original_untouched(tmp_path):
    meta_path = write_clip(tmp_path)
    before = (tmp_path / "clip1.mp4").read_bytes()

    with pytest.raises(OSError):
        trim_clip(meta_path, 2.0, 9.0, ffmpeg_path=tmp_path / "no-such-ffmpeg.exe", thumbnail=ThumbnailConfig())

    assert (tmp_path / "clip1.mp4").read_bytes() == before
    assert "trimmed" not in json.loads(meta_path.read_text(encoding="utf-8"))
    assert not list(tmp_path.glob("*.trim.mp4"))
