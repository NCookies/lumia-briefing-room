"""클립 영상 경로 → 클립(정보가 있는 것 + 앱이 만들지 않은 것) 색인. 클립 정리·카테고리 API 가 같이 쓴다."""

from __future__ import annotations

import os
from pathlib import Path

from lumia_briefing_room.api.clips import ClipSummary, find_clip, scan_clips
from lumia_briefing_room.api.unknown_clips import summary_of as summary_of_unknown
from lumia_briefing_room.config import Config, discover_ffmpeg, resolve_paths
from lumia_briefing_room.pipeline.clip_files import find_unknown, unknown_videos


def norm(path: Path) -> str:
    return os.path.normcase(str(path))


def summaries_by_video(cfg: Config) -> dict[str, ClipSummary]:
    resolved = resolve_paths(cfg.paths)
    libraries = (resolved.library_steam, resolved.library_vod)
    found: dict[str, ClipSummary] = {}
    for library in libraries:
        for clip in scan_clips(library, resolved.clip_roots):
            found[norm(clip.video)] = clip
    ffmpeg = discover_ffmpeg()
    for unknown in unknown_videos(libraries, resolved.clip_roots):
        found[norm(unknown.path)] = summary_of_unknown(unknown, resolved.library_steam, ffmpeg)
    return found


def locate_clip(cfg: Config, clip_id: str) -> ClipSummary | None:
    resolved = resolve_paths(cfg.paths)
    for library in (resolved.library_steam, resolved.library_vod):
        clip = find_clip(library, clip_id, resolved.clip_roots)
        if clip is not None:
            return clip
    unknown = find_unknown(clip_id, (resolved.library_steam, resolved.library_vod), resolved.clip_roots)
    if unknown is not None:
        return summary_of_unknown(unknown, resolved.library_steam, discover_ffmpeg())
    return None
