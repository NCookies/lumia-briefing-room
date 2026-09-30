"""풀영상이 없는 게임(이전 버전에서 분석한 게임 등)을 원본 녹화에서 다시 분석해 풀영상·후보·마커를 새로 만든다. (plan-fullvideo.md §3.6-d)

저장된 클립은 그대로 두고 다시 자르지 않는다(`process_match(existing_clip_ids=…)`). 새 결과가 나오지 않으면 기존 게임 기록을 그대로 둔다.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from lumia_briefing_room.config import Config
from lumia_briefing_room.pipeline.backfill_runtime import staging_config
from lumia_briefing_room.pipeline.game_files import GameNotFound, has_full_video, load_game, update_game
from lumia_briefing_room.pipeline.legacy_games import adopt_legacy_clips, saved_clip_ids
from lumia_briefing_room.pipeline.orchestrator import process_match
from lumia_briefing_room.video.segments import existing_segment_numbers, segment_number_at
from lumia_briefing_room.video.session import RecordingSession

log = logging.getLogger(__name__)

START_PROBE_SEGMENTS = 2
STAGING_DIRNAME = ".staging"


class RebuildError(Exception):
    """만들 수 없는 이유를 사용자에게 그대로 보여 줄 수 있는 문장으로 담는다."""


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def _session_and_range(
    game: dict, recording_root: Path | None, load_session: Callable[[Path], RecordingSession]
) -> tuple[RecordingSession, datetime, datetime]:
    if recording_root is None:
        raise RebuildError("스팀 녹화 폴더를 찾을 수 없습니다")
    start, end = _parse(game.get("matchStartUtc")), _parse(game.get("matchEndUtc"))
    if not game.get("sessionDir") or start is None:
        raise RebuildError("이 게임의 원본 녹화 정보가 없어 풀영상을 만들 수 없습니다")
    if end is None:
        raise RebuildError("게임 종료 시각을 몰라 풀영상을 만들 수 없습니다")
    session_dir = recording_root / game["sessionDir"]
    if not session_dir.is_dir():
        raise RebuildError("원본 녹화가 이미 삭제되어 풀영상을 만들 수 없습니다")
    try:
        session = load_session(session_dir)
        first = segment_number_at(session, start)
        alive = existing_segment_numbers(session, 0, first, first + START_PROBE_SEGMENTS)
    except Exception as exc:
        raise RebuildError("원본 녹화를 읽을 수 없어 풀영상을 만들 수 없습니다") from exc
    if not alive:
        raise RebuildError("원본 녹화가 이미 삭제되어 풀영상을 만들 수 없습니다")
    return session, start, end


def can_rebuild(
    game: dict, games_dir: Path, recording_root: Path | None,
    load_session: Callable[[Path], RecordingSession] = RecordingSession.load,
) -> bool:
    """풀영상이 없고(자동 정리로 지운 게임은 제외) 원본 녹화가 링버퍼에 남아 있다."""
    key = game.get("gameKey") or ""
    if game.get("fullVideoDeletedAt") or has_full_video(games_dir, key):
        return False
    try:
        _session_and_range(game, recording_root, load_session)
    except RebuildError:
        return False
    return True


def rebuild_full_video(
    *,
    games_dir: Path,
    clips_dir: Path,
    key: str,
    recording_root: Path | None,
    cfg: Config,
    ffmpeg_path: Path,
    process: Callable = process_match,
    load_session: Callable[[Path], RecordingSession] = RecordingSession.load,
    on_progress: Callable[[float], None] | None = None,
    cancel=None,
) -> None:
    try:
        game = load_game(games_dir, key)
    except GameNotFound as exc:
        raise RebuildError("게임을 찾을 수 없습니다") from exc
    if game.get("fullVideoDeletedAt") or has_full_video(games_dir, key):
        raise RebuildError("이미 풀영상이 있는 게임입니다")
    session, start, end = _session_and_range(game, recording_root, load_session)

    known = saved_clip_ids(game, clips_dir)
    staging = clips_dir / STAGING_DIRNAME / uuid.uuid4().hex
    staging.mkdir(parents=True, exist_ok=True)
    try:
        process(
            session, start, end, staging_config(cfg), ffmpeg_path=ffmpeg_path, clips_dir=staging, games_dir=games_dir,
            existing_clip_ids=known, on_progress=on_progress, cancel=cancel,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    if not has_full_video(games_dir, key):
        raise RebuildError(load_game(games_dir, key).get("fullVideoError") or "풀영상을 만들지 못했습니다")

    try:
        adopt_legacy_clips(games_dir, game, key)
    except Exception:
        log.exception("옛 클립을 새 후보에 잇지 못했다: %s", key)

    if game.get("pinned"):
        update_game(games_dir, key, lambda d: d.update(pinned=True))
