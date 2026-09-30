"""로그에 없는 과거 경기를 스팀 녹화만으로 찾아 클립으로 만든다. (plan-backfill.md B3·B4)

세션마다 화면을 훑어 경기 구간을 찾고(session_scan), 이미 아는 경기는 빼고, 오래된 것부터 한 경기씩 처리한다.
한 경기는 스테이징 폴더에 다 만든 뒤 클립 폴더로 옮기므로 도중에 취소·종료돼도 깨진 클립이 목록에 뜨지 않는다.
끝낸 경기는 상태 파일에 남기고, 판독은 캐시에 이어 쓰므로 다시 실행하면 이어서 한다.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from lumia_briefing_room.pipeline.backfill_progress import (
    DEFAULT_SCAN_SPEEDUP,
    AdaptiveGameDuration,
    MonotonicProgress,
    compute_workload,
    estimate_game_count,
    overall_fraction,
)
from lumia_briefing_room.pipeline.game_files import has_full_video, list_games
from lumia_briefing_room.pipeline.session_scan import GameWindow, ScanCancelled, window_key

log = logging.getLogger("lumia_briefing_room.backfill")

KNOWN_TOLERANCE_SEC = 240.0
MAX_ATTEMPTS = 3
STATE_FILE = "backfill.json"
STAGING_PREFIX = "game_"


class GameCancelled(Exception):
    """경기 하나를 처리하다 취소됐다. 스테이징은 버려지고 그 경기는 다음에 처음부터 다시 한다."""


class Scanner(Protocol):
    def list_sessions(self) -> list[Path]: ...

    def session_video_seconds(self, session_dir: Path) -> float: ...

    def scan(
        self, session_dir: Path, cancel: threading.Event | None, on_progress: Callable[[float, str], None]
    ) -> list[GameWindow]: ...


ProcessWindow = Callable[
    [Path, GameWindow, Path, threading.Event | None, Callable[[float], None] | None], list[Path]
]


@dataclass(frozen=True)
class BackfillProgress:
    phase: str
    fraction: float
    message: str = ""
    session_index: int = 0
    session_total: int = 0
    games_done: int = 0
    games_total: int = 0
    clips: int = 0


@dataclass
class BackfillResult:
    sessions_scanned: int = 0
    games_found: int = 0
    games_processed: int = 0
    games_failed: int = 0
    clips_created: int = 0
    cancelled: bool = False
    skipped: dict[str, int] = field(default_factory=lambda: {
        "known": 0, "cut_at_start": 0, "still_running": 0, "already_done": 0, "gave_up": 0,
    })


def _parse_utc(text: object) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _starts_in(folder: Path) -> list[datetime]:
    starts = []
    if not folder.is_dir():
        return starts
    for path in folder.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        start = _parse_utc(data.get("matchStartUtc")) if isinstance(data, dict) else None
        if start is not None:
            starts.append(start)
    return starts


def collect_known_starts(clips_dir: Path, games_dir: Path | None = None) -> list[datetime]:
    """이미 처리한 경기의 시작 시각. 같은 경기를 두 번 만들지 않는 기준이다.

    `games_dir` 를 주면 **풀영상이 있는(또는 자동 정리로 지운) 게임만** 처리된 것으로 본다. 풀영상이 없는 게임(이전 버전에서 클립만
    만든 게임, 풀영상 저장에 실패한 게임)은 원본이 남아 있으면 풀영상을 새로 만든다. 클립·휴지통·게임 기록에만 있고 게임 기록
    (`game.json`)이 없는 경기(휴지통에 버린 게임 등)는 처리된 것으로 본다. 안 주면 예전 방식(클립·휴지통·게임 기록이 있으면 처리됨).
    """
    clip_side = [s for folder in (clips_dir, clips_dir / ".trash", clips_dir / ".games") for s in _starts_in(folder)]
    if games_dir is None:
        return clip_side
    done, tracked = [], []
    for game in list_games(games_dir):
        start = _parse_utc(game.get("matchStartUtc"))
        if start is None:
            continue
        tracked.append(start)
        if game.get("fullVideoDeletedAt") or has_full_video(games_dir, game.get("gameKey") or ""):
            done.append(start)
    return done + [s for s in clip_side if s not in tracked]


def overlaps_known(window: GameWindow, known_starts: list[datetime]) -> bool:
    """알려진 경기 시작이 이 구간 안(또는 로딩 시간만큼 앞)에 있으면 같은 경기다."""
    lo = window.start_utc - timedelta(seconds=KNOWN_TOLERANCE_SEC)
    return any(lo <= start <= window.end_utc for start in known_starts)


class _State:
    """끝낸 경기와 실패 횟수. 원자적으로 저장해 중간에 꺼져도 깨지지 않는다."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.done: set[str] = set()
        self.failures: dict[str, int] = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.done = set(data.get("done", []))
                self.failures = {k: int(v) for k, v in data.get("failures", {}).items()}
            except (OSError, ValueError, TypeError):
                pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"done": sorted(self.done), "failures": self.failures}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)


def _staging_name(key: str) -> str:
    return STAGING_PREFIX + re.sub(r"[^0-9A-Za-z_-]", "_", key)


def clean_staging(staging_root: Path) -> None:
    """이전 실행이 도중에 죽어 남긴 스테이징을 치운다."""
    if staging_root.is_dir():
        for child in staging_root.iterdir():
            shutil.rmtree(child, ignore_errors=True)


def commit_staging(staging: Path, clips_dir: Path) -> int:
    """만든 클립을 클립 폴더로 옮긴다. mp4 → 썸네일·결과표 이미지 → json 순서라, json 이 보일 때는 나머지가 다 있다."""
    clips_dir.mkdir(parents=True, exist_ok=True)
    moved_json = 0
    ordered = [p for p in sorted(staging.rglob("*")) if p.is_file()]
    ordered.sort(key=lambda p: (p.suffix == ".json", p.suffix != ".mp4"))
    for path in ordered:
        target = clips_dir / path.relative_to(staging)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
        if path.suffix == ".json":
            moved_json += 1
    return moved_json


def run_backfill(
    *,
    scanner: Scanner,
    process_window: ProcessWindow,
    clips_dir: Path,
    state_dir: Path,
    staging_root: Path,
    known_starts: list[datetime],
    cancel: threading.Event | None = None,
    on_progress: Callable[[BackfillProgress], None] | None = None,
    scan_speedup: float = DEFAULT_SCAN_SPEEDUP,
) -> BackfillResult:
    """B8(plan-backfill.md §0): 진행률은 "예상 작업 시간" 비율로 계산하고(스캔=영상 길이÷배속,
    분석=게임 수×게임당 평균 시간), 재계산으로 계산값이 줄어도 화면 표시값은 단조 증가만 한다."""
    result = BackfillResult()
    state = _State(state_dir / STATE_FILE)
    clean_staging(staging_root)
    monotonic = MonotonicProgress()
    adaptive = AdaptiveGameDuration()

    def cancelled() -> bool:
        return cancel is not None and cancel.is_set()

    def report(phase: str, fraction: float, message: str = "", **extra) -> None:
        if on_progress is not None:
            on_progress(BackfillProgress(phase, monotonic.push(fraction), message, **extra))

    sessions = scanner.list_sessions()
    total_sessions = len(sessions)
    video_seconds = {s: scanner.session_video_seconds(s) for s in sessions}
    total_video_sec = sum(video_seconds.values())
    scanned_video_sec = 0.0
    todo: list[tuple[str, Path, GameWindow]] = []

    for index, session_dir in enumerate(sessions, start=1):
        if cancelled():
            result.cancelled = True
            return result

        session_len = video_seconds[session_dir]

        def scan_progress(fraction: float, message: str, _i=index, _len=session_len) -> None:
            elapsed_video_sec = scanned_video_sec + _len * fraction
            workload = compute_workload(
                video_seconds=total_video_sec, speedup=scan_speedup,
                game_count=estimate_game_count(total_video_sec), avg_game_sec=adaptive.estimate,
            )
            report(
                "scan", overall_fraction(elapsed_video_sec / scan_speedup, workload), message,
                session_index=_i, session_total=total_sessions,
            )

        try:
            windows = scanner.scan(session_dir, cancel, scan_progress)
        except ScanCancelled:
            result.cancelled = True
            return result
        result.sessions_scanned += 1
        result.games_found += len(windows)
        scanned_video_sec += session_len

        for window in windows:
            key = window_key(session_dir.name, window)
            if window.still_running:
                result.skipped["still_running"] += 1
            elif window.cut_at_start:
                result.skipped["cut_at_start"] += 1
            elif key in state.done:
                result.skipped["already_done"] += 1
            elif state.failures.get(key, 0) >= MAX_ATTEMPTS:
                result.skipped["gave_up"] += 1
            elif overlaps_known(window, known_starts):
                result.skipped["known"] += 1
            else:
                todo.append((key, session_dir, window))

    todo.sort(key=lambda item: item[2].hud_start_utc)
    total_games = len(todo)

    def analysis_workload():
        # 스캔이 끝나 실제 게임 수를 알므로, 스캔 전의 세션 길이 추정 대신 이 값으로 다시 계산한다.
        return compute_workload(
            video_seconds=total_video_sec, speedup=scan_speedup,
            game_count=total_games, avg_game_sec=adaptive.estimate,
        )

    scan_done_sec = total_video_sec / scan_speedup
    report(
        "process", overall_fraction(scan_done_sec, analysis_workload()), f"게임 {total_games}개",
        session_index=total_sessions, session_total=total_sessions, games_total=total_games,
    )

    for done, (key, session_dir, window) in enumerate(todo):
        if cancelled():
            result.cancelled = True
            return result

        def game_progress(internal_fraction: float, _done=done) -> None:
            elapsed = scan_done_sec + (_done + internal_fraction) * adaptive.estimate
            report(
                "process", overall_fraction(elapsed, analysis_workload()),
                f"{window.hud_start_utc.astimezone().strftime('%m-%d %H:%M')} 게임",
                session_index=total_sessions, session_total=total_sessions,
                games_done=_done, games_total=total_games, clips=result.clips_created,
            )

        game_progress(0.0)
        staging = staging_root / _staging_name(key)
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        started_at = time.monotonic()
        try:
            process_window(session_dir, window, staging, cancel, game_progress)
        except GameCancelled:
            shutil.rmtree(staging, ignore_errors=True)
            result.cancelled = True
            return result
        except Exception:
            adaptive.record(time.monotonic() - started_at)
            log.exception("과거 경기 분석 실패: %s", key)
            shutil.rmtree(staging, ignore_errors=True)
            state.failures[key] = state.failures.get(key, 0) + 1
            state.save()
            result.games_failed += 1
            continue

        adaptive.record(time.monotonic() - started_at)
        result.clips_created += commit_staging(staging, clips_dir)
        shutil.rmtree(staging, ignore_errors=True)
        state.done.add(key)
        state.failures.pop(key, None)
        state.save()
        result.games_processed += 1

    report(
        "done", 1.0, "", session_index=total_sessions, session_total=total_sessions, games_done=total_games,
        games_total=total_games, clips=result.clips_created,
    )
    return result
