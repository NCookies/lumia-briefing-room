import subprocess
import tempfile
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from lumia_briefing_room.config import ClipConfig
from lumia_briefing_room.detect.types import CombatInterval
from lumia_briefing_room.video.frames import write_merged_segment_file
from lumia_briefing_room.video.segments import segment_time_range
from lumia_briefing_room.video.session import RecordingSession


class ClipCutError(Exception):
    """요청한 구간에 세그먼트가 하나도 없을 때."""


@dataclass(frozen=True)
class ClipRange:
    start: float
    end: float
    preroll_source: str  # "combat" — SPEC §3 클립 메타데이터의 prerollSource


def resolve_clip_range(interval: CombatInterval, cfg: ClipConfig) -> ClipRange:
    """SPEC §3 클립 구간: 교전 시작 -preroll ~ 교전 종료 +postroll, 상한 적용."""
    start = max(0.0, interval.start - cfg.preroll_sec)
    end = interval.end + cfg.postroll_sec
    if end - start > cfg.max_duration_sec:
        end = start + cfg.max_duration_sec
    return ClipRange(start=start, end=end, preroll_source="combat")


def merge_overlapping(ranges: list[ClipRange], gap: float) -> list[ClipRange]:
    """SPEC §3: 겹치거나 mergeGapSec 이내로 가까운 구간을 하나로 합친다."""
    if not ranges:
        return []
    ordered = sorted(ranges, key=lambda r: r.start)
    merged = [ordered[0]]
    for r in ordered[1:]:
        last = merged[-1]
        if r.start <= last.end + gap:
            merged[-1] = ClipRange(
                start=last.start, end=max(last.end, r.end), preroll_source=last.preroll_source
            )
        else:
            merged.append(r)
    return merged


@dataclass(frozen=True)
class CutResult:
    segment_start: int
    segment_end: int
    duration_sec: float
    source_incomplete: bool
    audio_status: str = "full"


def audio_input_args(video_run: list[int], audio_run: list[int], segment_duration: float) -> list[str]:
    """오디오 조각이 비디오보다 늦게(또는 일찍) 시작하면 그만큼 밀어서 싱크를 맞춘다.

    오디오 조각이 중간에 비면 가장 긴 연속 구간만 쓰는데, 그걸 클립 0초에 그대로 붙이면
    소리가 화면과 어긋난다.
    """
    offset = (audio_run[0] - video_run[0]) * segment_duration
    if offset > 0:
        return ["-itsoffset", f"{offset:.3f}"]
    if offset < 0:
        return ["-ss", f"{-offset:.3f}"]
    return []


def audio_status(video_run: list[int], audio_run: list[int]) -> str:
    if not audio_run:
        return "none"
    covers = audio_run[0] <= video_run[0] and audio_run[-1] >= video_run[-1]
    return "full" if covers else "partial"


def cut_clip(
    session: RecordingSession,
    clip_range: ClipRange,
    out_path: Path,
    *,
    ffmpeg_path: Path,
    stream_video: int = 0,
    stream_audio: int = 1,
    include_audio: bool = True,
    tmp_dir: Path | None = None,
) -> CutResult:
    """SPEC §3 `[필요한 세그먼트만 복사 -> 병합 -> ffmpeg -c copy 컷]`.

    research §2.4: init + 연속 세그먼트를 이어붙이면 그대로 유효한 fMP4 다.
    gap 이 있으면 가장 긴 연속 구간만 쓰고 source_incomplete=True 로 표시한다
    (SPEC §7.2.1 부분 소실).
    """
    seg_range = segment_time_range(
        session,
        session.start_utc + timedelta(seconds=clip_range.start),
        session.start_utc + timedelta(seconds=clip_range.end),
    )
    numbers = seg_range.numbers()

    with tempfile.TemporaryDirectory(dir=tmp_dir, prefix="lumia_cut_") as td:
        td_path = Path(td)
        video_path = td_path / "video.mp4"
        used_video = write_merged_segment_file(session, stream_video, numbers, video_path)
        if not used_video:
            raise ClipCutError(
                f"세그먼트를 찾을 수 없다: {seg_range.first}-{seg_range.last}"
            )

        cmd = [str(ffmpeg_path), "-hide_banner", "-v", "error", "-y", "-i", str(video_path)]
        map_args = ["-map", "0:v:0"]

        used_audio: list[int] = []
        if include_audio:
            audio_path = td_path / "audio.mp4"
            used_audio = write_merged_segment_file(session, stream_audio, numbers, audio_path)
            if used_audio:
                cmd += audio_input_args(used_video, used_audio, session.segment_duration_sec)
                cmd += ["-i", str(audio_path)]
                map_args += ["-map", "1:a:0"]

        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd += map_args + ["-c", "copy", str(out_path)]
        subprocess.run(cmd, check=True, capture_output=True)

    gaps = seg_range.gaps(used_video)
    source_incomplete = bool(gaps)

    return CutResult(
        segment_start=used_video[0],
        segment_end=used_video[-1],
        duration_sec=(used_video[-1] - used_video[0] + 1) * session.segment_duration_sec,
        source_incomplete=source_incomplete,
        audio_status=audio_status(used_video, used_audio),
    )


def make_thumbnail(
    clip_path: Path,
    out_path: Path,
    *,
    duration_sec: float,
    offset_ratio: float,
    width: int,
    ffmpeg_path: Path,
) -> None:
    """SPEC §7.5: 클립 길이의 offset_ratio 지점을 썸네일로 뽑는다.

    ffprobe 없이 duration_sec 을 직접 받는다 — 어차피 cut_clip 이 이미 알고 있다.
    """
    offset = max(0.0, min(duration_sec, duration_sec * offset_ratio))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(ffmpeg_path), "-hide_banner", "-v", "error", "-y",
        "-ss", f"{offset:.3f}", "-i", str(clip_path),
        "-frames:v", "1", "-vf", f"scale={width}:-1",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
