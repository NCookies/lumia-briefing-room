"""게임 하나를 원본 녹화에서 다시 분석한다.

새 클립은 임시 폴더(스테이징)에 만들고, 분석이 성공해 클립이 하나라도 나온 뒤에만
기존 클립을 지우고 새 클립을 실제 위치로 옮긴다. 실패하거나 클립이 하나도 안 나오면
스테이징만 지우고 기존 클립은 그대로 둔다(docs/plan-ui.md §0-(6))."""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from lumia_briefing_room.config import Config
from lumia_briefing_room.pipeline.delete_helper import delete_clip
from lumia_briefing_room.pipeline.label_archive import archive_dir_for
from lumia_briefing_room.pipeline.label_migrate import load_metas, migrate_labels
from lumia_briefing_room.pipeline.orchestrator import process_match
from lumia_briefing_room.pipeline.playerlog import MatchBoundary
from lumia_briefing_room.video.segments import existing_segment_numbers, segment_number_at
from lumia_briefing_room.video.session import RecordingSession

log = logging.getLogger(__name__)

END_MATCH_TOLERANCE = timedelta(seconds=2)
START_PROBE_SEGMENTS = 2
STAGING_DIRNAME = ".staging"


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


def _move_staged_tree(staging: Path, dest_root: Path) -> list[Path]:
    """스테이징 폴더의 파일을 상대 구조를 유지하며 실제 클립 폴더로 옮기고, 스테이징을 지운다."""
    moved: list[Path] = []
    for path in sorted(staging.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(staging)
        dest = dest_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest))
        moved.append(dest)
    shutil.rmtree(staging, ignore_errors=True)
    return moved


def reprocess_game(
    *,
    clips_dir: Path,
    ref: GameRef,
    recording_root: Path,
    boundaries: list[MatchBoundary],
    cfg: Config,
    ffmpeg_path: Path,
    process: Callable = process_match,
    load_session: Callable[[Path], RecordingSession] = RecordingSession.load,
    guard=None,
) -> list[Path]:
    """`guard` 는 기존 클립을 지우고 새 클립을 옮기는 구간만 감싸는 락이다(오래 걸리는 분석 동안은 잡지 않는다)."""
    guard = guard or contextlib.nullcontext()

    old = _game_meta_paths(clips_dir, ref)
    if not old:
        raise ReprocessError("이 게임의 클립을 찾을 수 없습니다")

    session_dir = recording_root / ref.session_name
    if not session_dir.exists():
        raise ReprocessError("원본 녹화가 이미 삭제되어 다시 분석할 수 없습니다")
    session = load_session(session_dir)

    start = _parse(ref.match_start)
    old_metas = load_metas(old)
    recorded_end = json.loads(old[0].read_text(encoding="utf-8")).get("matchEndUtc")
    end = _parse(recorded_end) if recorded_end else find_match_end(start, boundaries)
    if end is None:
        raise ReprocessError("게임 종료 시각을 로그에서 찾을 수 없어 다시 분석할 수 없습니다")

    first = segment_number_at(session, start)
    if not existing_segment_numbers(session, 0, first, first + START_PROBE_SEGMENTS):
        raise ReprocessError("원본 녹화가 이미 삭제되어 다시 분석할 수 없습니다")

    staging = clips_dir / STAGING_DIRNAME / uuid.uuid4().hex
    staging.mkdir(parents=True, exist_ok=True)
    try:
        written = process(session, start, end, cfg, ffmpeg_path=ffmpeg_path, clips_dir=staging)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    if not written:
        shutil.rmtree(staging, ignore_errors=True)
        raise ReprocessError("다시 분석했지만 이 게임에서 클립을 찾지 못했습니다. 기존 클립을 그대로 둡니다")

    try:
        report = migrate_labels(old_metas, list(written))
        log.info("라벨 이관: %s", report)
    except Exception:
        log.exception("라벨 이관에 실패했다 - 새 클립은 라벨 없이 둔다")

    with guard:
        archive_dir = archive_dir_for(clips_dir)
        for path in old:
            delete_clip(path, mode=cfg.ui.delete_mode, archive_dir=archive_dir)
        final = _move_staged_tree(staging, clips_dir)

    return sorted(p for p in final if p.suffix == ".json")
