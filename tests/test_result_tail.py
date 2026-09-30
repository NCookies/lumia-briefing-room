import subprocess
from pathlib import Path

import numpy as np
import pytest

from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.pipeline import result_tail
from lumia_briefing_room.pipeline.result_tail import find_result_in_video, result_from_frames
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.vod import find_ffprobe

try:
    from lumia_briefing_room.config import discover_ffmpeg

    FFMPEG_PATH = discover_ffmpeg()
except Exception:  # pragma: no cover
    FFMPEG_PATH = None

requires_ffmpeg = pytest.mark.skipif(
    FFMPEG_PATH is None or find_ffprobe(FFMPEG_PATH) is None, reason="ffmpeg/ffprobe를 찾을 수 없다"
)


def result(placement):
    return ResultScreen(placement=placement, total=7, match_type="normal", match_label="일반", outcome="실험 종료", nickname="나")


def gen(tags):
    for n, tag in enumerate(tags):
        yield n, np.full((2, 2, 3), tag, dtype=np.uint8)


def test_result_from_frames_merges_the_result_screen_frames_and_ignores_the_rest():
    reads = {9: result(3), 8: result(None)}

    got = result_from_frames(
        gen([1, 9, 8, 9, 1, 1, 1, 9]), lambda f: reads.get(int(f[0, 0, 0])), is_ingame=lambda f: False
    )

    assert got.placement == 3


def test_result_from_frames_closes_the_source_when_done():
    closed = []

    class Source:
        def __iter__(self):
            return gen([9, 1, 1, 1, 1, 1])

        def close(self):
            closed.append(True)

    result_from_frames(Source(), lambda f: result(3) if int(f[0, 0, 0]) == 9 else None, is_ingame=lambda f: False)

    assert closed == [True]


@requires_ffmpeg
def test_find_result_in_video_reads_the_tail_of_a_real_file(tmp_path, monkeypatch):
    path = tmp_path / "full.mp4"
    subprocess.run(
        [
            str(FFMPEG_PATH), "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10",
            "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
    )
    seen = []
    monkeypatch.setattr(result_tail, "read_result_screen", lambda f, p, r: seen.append(f.shape) or result(2))
    monkeypatch.setattr(result_tail, "make_is_ingame", lambda *a, **k: (lambda f: False))
    profile = ResolutionProfile.for_resolution(2560, 1440)

    got = find_result_in_video(path, ffmpeg_path=FFMPEG_PATH, profile=profile, reader=object(), tail_sec=3, fps=2)

    assert got.placement == 2
    assert seen and seen[0] == (48, 64, 3)
