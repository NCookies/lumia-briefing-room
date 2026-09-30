"""앱이 만들지 않은 영상(OBS 녹화 등)을 클립 목록에 올린다. (plan-fullvideo.md §3.9)

클립 폴더 안의 영상 파일이면 정보 파일이 없어도 클립으로 본다. 제목은 파일 이름, 길이는 영상에서 읽고(캐시), 썸네일은 처음 볼 때 만든다.
게임 정보·태그는 없다. 제목이나 라벨을 고치면 그때 정보 파일(`x_<지문>.json`)이 생기고, 그 뒤에는 내용 지문으로 이어진다.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

from lumia_briefing_room.api.clips import ClipSummary
from lumia_briefing_room.config import EncodeConfig
from lumia_briefing_room.pipeline.clip import make_thumbnail
from lumia_briefing_room.pipeline.clip_files import UnknownVideo, content_fingerprint
from lumia_briefing_room.video.vod import find_ffprobe, probe_video

THUMBS = ".thumbs"
_durations: dict[str, tuple[int, int, float]] = {}
_lock = threading.Lock()


def probe_duration(path: Path, ffmpeg: Path | None) -> float:
    if ffmpeg is None:
        return 0.0
    try:
        return probe_video(path, ffprobe_path=find_ffprobe(ffmpeg)).duration_sec
    except Exception:
        return 0.0


def duration_of(path: Path, ffmpeg: Path | None) -> float:
    try:
        stat = path.stat()
    except OSError:
        return 0.0
    with _lock:
        hit = _durations.get(str(path))
    if hit and hit[0] == stat.st_size and hit[1] == stat.st_mtime_ns:
        return hit[2]
    value = probe_duration(path, ffmpeg)
    if value > 0:
        with _lock:
            _durations[str(path)] = (stat.st_size, stat.st_mtime_ns, value)
    return value


def base_id(unknown_id: str) -> str:
    return unknown_id.partition("~")[0]


def summary_of(video: UnknownVideo, library: Path, ffmpeg: Path | None) -> ClipSummary:
    """정보 파일이 없는 영상의 가짜 클립. `meta_path` 는 나중에 정보를 고칠 때 만들어질 자리(복사본은 같은 정보를 같이 쓴다)."""
    stat = video.path.stat()
    fingerprint = content_fingerprint(video.path)
    meta = {
        "title": video.path.stem, "source": "other", "tags": [], "unknownVideo": True,
        "durationSec": duration_of(video.path, ffmpeg), "thumbnailPath": f"{THUMBS}/{base_id(video.id)}.jpg",
        "videoFingerprint": fingerprint, "videoSizeBytes": stat.st_size,
    }
    return ClipSummary(
        id=video.id, meta_path=library / f"{base_id(video.id)}.json", meta=meta, size_bytes=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc), video_path=video.path,
    )


def ensure_thumbnail(clip: ClipSummary, encode: EncodeConfig, ffmpeg: Path | None) -> Path | None:
    """캐시된 썸네일을 돌려주고, 없으면 영상에서 만든다. 만들 수 없으면 None."""
    target = clip.meta_path.parent / THUMBS / f"{base_id(clip.id)}.jpg"
    if target.is_file():
        return target
    if ffmpeg is None or not clip.video.is_file():
        return None
    try:
        make_thumbnail(
            clip.video, target, duration_sec=float(clip.meta.get("durationSec") or 0.0),
            offset_ratio=encode.thumbnail.offset_ratio, width=encode.thumbnail.width, ffmpeg_path=ffmpeg,
        )
    except Exception:
        return None
    return target if target.is_file() else None
