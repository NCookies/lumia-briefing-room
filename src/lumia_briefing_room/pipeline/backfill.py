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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from lumia_briefing_room.pipeline.session_scan import GameWindow, ScanCancelled, window_key

log = logging.getLogger("lumia_briefing_room.backfill")

KNOWN_TOLERANCE_SEC = 120.0
MAX_ATTEMPTS = 3
STATE_FILE = "backfill.json"
STAGING_PREFIX = "game_"


class GameCancelled(Exception):
    """경기 하나를 처리하다 취소됐다. 스테이징은 버려지고 그 경기는 다음에 처음부터 다시 한다."""


class Scanner(Protocol):
    def list_sessions(self) -> list[Path]: ...

    def scan(
        self, session_dir: Path, cancel: threading.Event | None, on_progress: Callable[[float, str], None]
    ) -> list[GameWindow]: ...


ProcessWindow = Callable[[Path, GameWindow, Path, threading.Event | None], list[Path]]


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


def collect_known_starts(clips_dir: Path) -> list[datetime]:
    """이미 클립이 있거나(휴지통 포함) 게임 기록이 남은 경기의 시작 시각. 같은 경기를 두 번 만들지 않는 기준이다."""
    starts = []
    for folder in (clips_dir, clips_dir / ".trash", clips_dir / ".games"):
        if not folder.is_dir():
            continue
        for path in folder.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            start = _parse_utc(data.get("matchStartUtc")) if isinstance(data, dict) else None
            if start is not None:
                starts.append(start)
    return starts


def overlaps_known(window: GameWindow, known_starts: list[datetime]) -> bool:
    """알려진 경기 시작이 이 구간 안(또는 로딩 시간만큼 앞)에 있으면 같은 경기다."""
    lo = window.hud_start_utc - timedelta(seconds=KNOWN_TOLERANCE_SEC)
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
) -> BackfillResult:
    result = BackfillResult()
    state = _State(state_dir / STATE_FILE)
    clean_staging(staging_root)

    def cancelled() -> bool:
        return cancel is not None and cancel.is_set()

    def report(phase: str, fraction: float, message: str = "", **extra) -> None:
        if on_progress is not None:
            on_progress(BackfillProgress(phase, min(1.0, max(0.0, fraction)), message, **extra))

    sessions = scanner.list_sessions()
    total_sessions = len(sessions)
    todo: list[tuple[str, Path, GameWindow]] = []

    for index, session_dir in enumerate(sessions, start=1):
        if cancelled():
            result.cancelled = True
            return result

        def scan_progress(fraction: float, message: str, _i=index) -> None:
            report(
                "scan", 0.5 * ((_i - 1 + fraction) / max(1, total_sessions)), message,
                session_index=_i, session_total=total_sessions,
            )

        try:
            windows = scanner.scan(session_dir, cancel, scan_progress)
        except ScanCancelled:
            result.cancelled = True
            return result
        result.sessions_scanned += 1
        result.games_found += len(windows)

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
    report("process", 0.5, f"게임 {total_games}개", session_total=total_sessions, games_total=total_games)

    for done, (key, session_dir, window) in enumerate(todo):
        if cancelled():
            result.cancelled = True
            return result
        base = 0.5 + 0.5 * (done / max(1, total_games))
        report(
            "process", base, f"{window.hud_start_utc.astimezone().strftime('%m-%d %H:%M')} 게임",
            session_total=total_sessions, games_done=done, games_total=total_games, clips=result.clips_created,
        )
        staging = staging_root / _staging_name(key)
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        try:
            process_window(session_dir, window, staging, cancel)
        except GameCancelled:
            shutil.rmtree(staging, ignore_errors=True)
            result.cancelled = True
            return result
        except Exception:
            log.exception("과거 경기 분석 실패: %s", key)
            shutil.rmtree(staging, ignore_errors=True)
            state.failures[key] = state.failures.get(key, 0) + 1
            state.save()
            result.games_failed += 1
            continue

        result.clips_created += commit_staging(staging, clips_dir)
        shutil.rmtree(staging, ignore_errors=True)
        state.done.add(key)
        state.failures.pop(key, None)
        state.save()
        result.games_processed += 1

    report(
        "done", 1.0, "", session_total=total_sessions, games_done=total_games,
        games_total=total_games, clips=result.clips_created,
    )
    return result
