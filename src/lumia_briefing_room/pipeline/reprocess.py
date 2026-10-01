"""게임 하나를 원본 녹화에서 다시 분석한다.

새 클립은 임시 폴더(스테이징)에 만들고, 분석이 성공해 클립이 하나라도 나온 뒤에만
기존 클립을 지우고 새 클립을 실제 위치로 옮긴다. 실패하거나 클립이 하나도 안 나오면
스테이징만 지우고 기존 클립은 그대로 둔다(docs/plan-ui.md §0-(6)).

사용자가 보관한 클립(`categories.is_user_archived` - 카테고리가 없는 옛 경로 모드는 전부)은 지우지 않는다.
그 클립과 3초 이상 겹치거나 ID 가 같은 새 클립은 만들지 않는다(ID 가 같으면 보관한 클립을 덮어쓴다)."""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from lumia_briefing_room.config import Config
from lumia_briefing_room.pipeline import categories
from lumia_briefing_room.pipeline.clip_files import commit_staged_clips, find_video_for
from lumia_briefing_room.pipeline.delete_helper import delete_clip
from lumia_briefing_room.pipeline.label_archive import archive_dir_for
from lumia_briefing_room.pipeline.label_migrate import MIN_OVERLAP_SEC, load_metas, migrate_labels, overlap
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
        if b.end_utc is not None and any(
            abs(t - start) <= END_MATCH_TOLERANCE for t in (b.start_utc, b.loading_utc)
        ):
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


def _apply_locked_result(written: list[Path], locked_result: dict | None) -> None:
    """사용자가 `manual` 로 잠근 순위·결과는 다시 분석해 새로 만든 클립에도 그대로 이어간다(SPEC §2.13 수동 보정)."""
    for path in written:
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta["matchResult"] = locked_result
        meta["matchResultSource"] = "manual"
        path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_saved_marks(data: dict, clip_ids: Iterable[str]) -> None:
    """게임 기록(`game.json`)에서 만들지 않은 클립에 걸린 저장됨 표시만 뗀다."""
    gone = set(clip_ids)
    for field in ("candidates", "userCandidates"):
        for cand in data.get(field) or []:
            user = cand.get("user") or {}
            if user.get("savedClipId") in gone:
                for key in ("savedClipId", "savedStart", "savedEnd"):
                    user.pop(key, None)
                cand["user"] = user


def _drop_new_clips_clashing_with_kept(staging: Path, written: list[Path], kept_metas: list[dict]) -> tuple[list[Path], list[str]]:
    """보관한 클립과 겹치거나 ID 가 같은 새 클립의 파일(영상·썸네일·json)을 스테이징에서 지운다. (남은 json, 지운 ID)."""
    kept_ids = {m["id"] for m in kept_metas}
    remaining: list[Path] = []
    dropped: list[str] = []
    for path in written:
        fresh = json.loads(path.read_text(encoding="utf-8"))
        clash = path.stem in kept_ids or any(
            overlap(fresh, m) >= MIN_OVERLAP_SEC for m in kept_metas
            if fresh.get("videoOffsetSec") is not None and m.get("videoOffsetSec") is not None
        )
        if not clash:
            remaining.append(path)
            continue
        for leftover in staging.rglob(f"{path.stem}.*"):
            leftover.unlink(missing_ok=True)
        dropped.append(path.stem)
    return remaining, dropped


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
    video_dir: Path | None = None,
    video_roots: Iterable[Path] = (),
    staging_root: Path | None = None,
    on_dropped: Callable[[list[str]], None] | None = None,
) -> list[Path]:
    """`clips_dir` 는 클립 정보(library) 폴더, `video_dir` 은 새 영상이 놓일 폴더(기본 `clips_dir`), `video_roots` 는 옛 영상을 찾을 자리,
    `staging_root` 는 작업 폴더를 만들 곳(기본 `clips_dir/.staging` - 영상이 놓일 드라이브에 두는 게 좋다).

    `on_dropped` 는 보관한 클립과 겹쳐 만들지 않은 새 클립의 ID 를 받는다(게임 기록의 저장됨 표시를 떼는 데 쓴다).
    `guard` 는 기존 클립을 지우고 새 클립을 옮기는 구간만 감싸는 락이다(오래 걸리는 분석 동안은 잡지 않는다)."""
    guard = guard or contextlib.nullcontext()

    old = _game_meta_paths(clips_dir, ref)
    if not old:
        raise ReprocessError("이 게임의 클립을 찾을 수 없습니다")

    old_metas = [json.loads(p.read_text(encoding="utf-8")) for p in old]
    locked_result = next(
        (m.get("matchResult") for m in old_metas if m.get("matchResultSource") == "manual"), None
    )

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

    staging = (staging_root or clips_dir / STAGING_DIRNAME) / uuid.uuid4().hex
    staging.mkdir(parents=True, exist_ok=True)
    try:
        written = process(session, start, end, cfg, ffmpeg_path=ffmpeg_path, clips_dir=staging)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    if not written:
        shutil.rmtree(staging, ignore_errors=True)
        raise ReprocessError("다시 분석했지만 이 게임에서 클립을 찾지 못했습니다. 기존 클립을 그대로 둡니다")

    roots = tuple(video_roots)
    kept_paths = [p for p in old if categories.is_user_archived(cfg, find_video_for(p, roots))]
    dropped: list[str] = []
    if kept_paths:
        written, dropped = _drop_new_clips_clashing_with_kept(staging, list(written), load_metas(kept_paths))
        if dropped:
            log.info("보관한 클립과 겹쳐 새 클립을 만들지 않았다: %s", dropped)

    try:
        report = migrate_labels(old_metas, list(written))
        log.info("라벨 이관: %s", report)
    except Exception:
        log.exception("라벨 이관에 실패했다 - 새 클립은 라벨 없이 둔다")

    if locked_result is not None:
        _apply_locked_result(written, locked_result)

    with guard:
        archive_dir = archive_dir_for(clips_dir)
        for path in (p for p in old if p not in kept_paths):
            delete_clip(
                path, mode=cfg.ui.delete_mode, archive_dir=archive_dir,
                video=find_video_for(path, roots),
            )
        final = commit_staged_clips(staging, clips_dir, video_dir or clips_dir)

    if dropped and on_dropped is not None:
        on_dropped(dropped)
    return sorted(final)
