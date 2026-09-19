from __future__ import annotations

import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lumia_briefing_room.config import discover_ffmpeg

FFMPEG_PATH = discover_ffmpeg()

requires_ffmpeg = pytest.mark.skipif(FFMPEG_PATH is None, reason="ffmpeg 를 찾을 수 없다")


@pytest.fixture
def ffmpeg_path() -> Path | None:
    return FFMPEG_PATH


@pytest.fixture
def make_synthetic_session():
    """테스트가 tmp_path 와 함께 호출할 세션 빌더 함수를 넘긴다."""
    return build_synthetic_session


def _read_top_level_boxes(data: bytes) -> list[tuple[bytes, int, int]]:
    boxes = []
    i = 0
    while i < len(data):
        size = struct.unpack(">I", data[i : i + 4])[0]
        boxtype = data[i + 4 : i + 8]
        if size == 0:
            size = len(data) - i
        boxes.append((boxtype, i, size))
        i += size
    return boxes


def build_synthetic_session(
    tmp_path: Path,
    *,
    width: int = 64,
    height: int = 48,
    fps: int = 10,
    segment_frames: int = 10,
    num_segments: int = 5,
    app_id: int = 999999,
    start_utc: datetime = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
) -> Path:
    """ffmpeg 로 실제 fMP4 를 만들어 init/chunk 파일로 쪼갠 뒤,
    RecordingSession.load() 가 읽을 수 있는 세션 폴더를 구성한다.

    -movflags frag_keyframe 는 키프레임마다 새 fragment(moof+mdat)를 만든다.
    -g/-keyint_min 을 segment_frames 로 고정하면 fragment 1개 = 세그먼트 1개가 된다
    (research.md §2.2: 실제 스팀 녹화도 세그먼트당 키프레임 1개, 3.000초 간격).
    """
    if FFMPEG_PATH is None:
        raise RuntimeError("ffmpeg 를 찾을 수 없다")

    total_frames = segment_frames * num_segments

    raw_mp4 = tmp_path / "_raw.mp4"
    subprocess.run(
        [
            str(FFMPEG_PATH),
            "-hide_banner",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={width}x{height}:rate={fps}",
            "-frames:v",
            str(total_frames),
            "-an",
            "-c:v",
            "libx264",
            "-g",
            str(segment_frames),
            "-keyint_min",
            str(segment_frames),
            "-sc_threshold",
            "0",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "frag_keyframe+empty_moov+default_base_moof",
            str(raw_mp4),
        ],
        check=True,
        capture_output=True,
    )

    data = raw_mp4.read_bytes()
    boxes = _read_top_level_boxes(data)

    first_moof = next(i for i, (t, _, _) in enumerate(boxes) if t == b"moof")
    init_bytes = data[: boxes[first_moof][1]]

    fragments: list[bytes] = []
    i = first_moof
    while i < len(boxes) and boxes[i][0] == b"moof":
        moof_type, moof_offset, moof_size = boxes[i]
        mdat_type, mdat_offset, mdat_size = boxes[i + 1]
        assert mdat_type == b"mdat"
        fragments.append(data[moof_offset : mdat_offset + mdat_size])
        i += 2

    assert len(fragments) == num_segments, (
        f"예상 세그먼트 {num_segments}개, 실제 {len(fragments)}개"
    )

    folder_name = f"bg_{app_id}_{start_utc:%Y%m%d}_{start_utc:%H%M%S}"
    session_dir = tmp_path / folder_name
    session_dir.mkdir()

    (session_dir / "init-stream0.m4s").write_bytes(init_bytes)
    for n, frag in enumerate(fragments, start=1):
        (session_dir / f"chunk-stream0-{n:05d}.m4s").write_bytes(frag)

    segment_duration_sec = segment_frames / fps
    mpd = f"""<?xml version="1.0" encoding="utf-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"
     type="dynamic"
     availabilityStartTime="{start_utc:%Y-%m-%dT%H:%M:%S}Z"
     timeShiftBufferDepth="PT2H0M0.0S"
     maxSegmentDuration="PT{segment_duration_sec}S">
    <Period id="0" start="PT0.0S">
        <AdaptationSet id="0" contentType="video" maxWidth="{width}" maxHeight="{height}">
            <Representation id="0" mimeType="video/mp4" width="{width}" height="{height}">
                <SegmentTemplate timescale="1000000" duration="{int(segment_duration_sec * 1_000_000)}"
                                 initialization="init-stream$RepresentationID$.m4s"
                                 media="chunk-stream$RepresentationID$-$Number%05d$.m4s"
                                 startNumber="1"/>
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>"""
    (session_dir / "session.mpd").write_text(mpd, encoding="utf-8")

    return session_dir
