"""게임 하나를 원본 녹화에서 다시 분석한다. 기존 클립은 휴지통으로 옮기고, 실패하면 되돌린다."""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from lumia_briefing_room.config import Config
from lumia_briefing_room.pipeline.orchestrator import process_match
from lumia_briefing_room.pipeline.playerlog import MatchBoundary
from lumia_briefing_room.pipeline.retention import restore_clip, trash_clip
from lumia_briefing_room.video.segments import existing_segment_numbers, segment_number_at
from lumia_briefing_room.video.session import RecordingSession

log = logging.getLogger(__name__)

END_MATCH_TOLERANCE = timedelta(seconds=2)
START_PROBE_SEGMENTS = 2


class ReprocessError(Exception):
    """다시 분석할 수 없는 이유를 사용자에게 그대로 보여 줄 수 있는 문장으로 담는다."""


@dataclass(frozen=True)
class GameRef:
    session_name: str
    match_start: str


def _parse(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def find_match_end(start: datetime, boundaries: list[MatchBoundary]) -> datetime | None:
    for b in boundaries:
        if b.end_utc is not None and abs(b.start_utc - start) <= END_MATCH_TOLERANCE:
            return b.end_utc
    return None


def _game_meta_paths(directory: Path, ref: GameRef) -> list[Path]:
    paths = []
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if meta.get("sessionDir") == ref.session_name and meta.get("matchStartUtc") == ref.match_start:
            paths.append(path)
    return paths


def _delete_clip_files(meta_path: Path) -> None:
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    for f in (meta_path.with_suffix(".mp4"), Path(meta["thumbnailPath"]) if meta.get("thumbnailPath") else None):
        if f is not None:
            f.unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)


def reprocess_game(
    *,
    clips_dir: Path,
    trash_dir: Path,
    ref: GameRef,
    recording_root: Path,
    boundaries: list[MatchBoundary],
    cfg: Config,
    ffmpeg_path: Path,
    process: Callable = process_match,
    load_session: Callable[[Path], RecordingSession] = RecordingSession.load,
    guard=None,
) -> list[Path]:
    """`guard` 는 클립 파일을 옮기는 구간만 감싸는 락이다(오래 걸리는 분석 동안은 잡지 않는다)."""
    guard = guard or contextlib.nullcontext()

    old = _game_meta_paths(clips_dir, ref)
    if not old:
        raise ReprocessError("이 게임의 클립을 찾을 수 없습니다")

    session_dir = recording_root / ref.session_name
    if not session_dir.exists():
        raise ReprocessError("원본 녹화가 이미 삭제되어 다시 분석할 수 없습니다")
    session = load_session(session_dir)

    start = _parse(ref.match_start)
    recorded_end = json.loads(old[0].read_text(encoding="utf-8")).get("matchEndUtc")
    end = _parse(recorded_end) if recorded_end else find_match_end(start, boundaries)
    if end is None:
        raise ReprocessError("게임 종료 시각을 로그에서 찾을 수 없어 다시 분석할 수 없습니다")

    first = segment_number_at(session, start)
    if not existing_segment_numbers(session, 0, first, first + START_PROBE_SEGMENTS):
        raise ReprocessError("원본 녹화가 이미 삭제되어 다시 분석할 수 없습니다")

    with guard:
        for path in _game_meta_paths(trash_dir, ref):
            if path.stem in {p.stem for p in old}:
                _delete_clip_files(path)
        trashed = [trash_clip(path, trash_dir) for path in old]

    try:
        return process(session, start, end, cfg, ffmpeg_path=ffmpeg_path, clips_dir=clips_dir)
    except Exception:
        log.exception("다시 분석 실패 - 기존 클립을 되돌린다")
        with guard:
            for path in _game_meta_paths(clips_dir, ref):
                _delete_clip_files(path)
            for path in trashed:
                restore_clip(path, clips_dir)
        raise
