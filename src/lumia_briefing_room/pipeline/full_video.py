"""게임 전체 영상(`games/<경기키>/full.mp4`)을 만든다. (plan-fullvideo.md §3.2, §3.4)"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from lumia_briefing_room.pipeline.clip import ClipCutError, ClipRange, CutResult, cut_clip
from lumia_briefing_room.pipeline.ffmpeg_errors import describe_clip_error
from lumia_briefing_room.pipeline.game_store import FULL_VIDEO, has_room
from lumia_briefing_room.video.segments import SegmentRange
from lumia_briefing_room.video.session import RecordingSession

log = logging.getLogger(__name__)

# 병합 중간물이 다른 드라이브(temp)에 있어도 최종 파일이 들어갈 곳에는 원본 크기만큼 필요하다. 여유분은 게임 하나 몫의 안전 폭이다.
MARGIN_BYTES = 512 * 1024 * 1024
_CHUNK = re.compile(r"^chunk-stream[01]-(\d{5})\.m4s$")


@dataclass(frozen=True)
class FullVideo:
    path: Path
    cut: CutResult
    size_bytes: int | None
    offset_sec: float  # 풀영상 0초가 세션 기준 몇 초인지


@dataclass(frozen=True)
class FullVideoOutcome:
    video: FullVideo | None
    error: str | None = None


def estimate_source_bytes(session: RecordingSession, seg_range: SegmentRange) -> int:
    total = 0
    try:
        entries = list(session.directory.iterdir())
    except OSError:
        return 0
    for path in entries:
        m = _CHUNK.match(path.name)
        if m and seg_range.first <= int(m.group(1)) <= seg_range.last:
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total


def _free_bytes(folder: Path) -> int:
    probe = folder
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def cut_full_video(
    session: RecordingSession,
    seg_range: SegmentRange,
    match_start: datetime,
    match_end: datetime,
    folder: Path,
    *,
    ffmpeg_path: Path,
    include_audio: bool,
    tmp_dir: Path,
    max_bytes_per_sec: float | None = None,
) -> FullVideoOutcome:
    """게임 전체 세그먼트를 `-c copy` 로 한 파일에 만든다. 실패해도 예외를 올리지 않는다 - 후보 기록과 클립 저장은 계속돼야 한다."""
    needed = estimate_source_bytes(session, seg_range)
    try:
        free = _free_bytes(folder)
    except OSError as exc:
        return FullVideoOutcome(None, f"저장 위치를 확인할 수 없습니다: {exc}")
    if not has_room(free_bytes=free, needed_bytes=needed, margin_bytes=MARGIN_BYTES):
        return FullVideoOutcome(
            None, f"저장 공간이 부족해 풀영상을 만들지 못했습니다 (필요 약 {needed / 2**30:.1f}GB, 여유 {free / 2**30:.1f}GB)."
        )

    folder.mkdir(parents=True, exist_ok=True)
    tmp_out = folder / "full.tmp.mp4"
    final = folder / FULL_VIDEO
    clip_range = ClipRange(
        start=(match_start - session.start_utc).total_seconds(),
        end=(match_end - session.start_utc).total_seconds(),
        preroll_source="combat",
    )
    try:
        cut = cut_clip(
            session, clip_range, tmp_out, ffmpeg_path=ffmpeg_path, include_audio=include_audio, tmp_dir=tmp_dir,
            max_bytes_per_sec=max_bytes_per_sec,
        )
        os.replace(tmp_out, final)
    except (ClipCutError, OSError, subprocess.CalledProcessError) as exc:
        tmp_out.unlink(missing_ok=True)
        message = describe_clip_error(exc)
        log.warning("풀영상 컷 실패 - 후보 기록과 클립 저장은 계속한다: %s", message)
        return FullVideoOutcome(None, message)

    try:
        size = final.stat().st_size
    except OSError:
        size = None
    offset = (cut.segment_start - 1) * session.segment_duration_sec
    return FullVideoOutcome(FullVideo(path=final, cut=cut, size_bytes=size, offset_sec=offset))
