"""`games/<경기키>/game.json` 읽기·수정. API 와 클립 저장이 함께 쓴다. (plan-fullvideo.md §3.1)"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from pathlib import Path

from lumia_briefing_room.pipeline.game_store import FULL_VIDEO, GAME_JSON, write_game_json

_KEY = re.compile(r"^(\d{8}_\d{6}|vod_[0-9a-f]{12}_g\d{2,})$")
_lock = threading.Lock()


class GameNotFound(Exception):
    pass


def valid_key(key: str) -> bool:
    return bool(_KEY.match(key))


def game_dir(games_dir: Path, key: str) -> Path:
    if not valid_key(key):
        raise GameNotFound(key)
    return games_dir / key


def load_game(games_dir: Path, key: str) -> dict:
    try:
        data = json.loads((game_dir(games_dir, key) / GAME_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GameNotFound(key) from exc
    if not isinstance(data, dict):
        raise GameNotFound(key)
    return data


def list_games(games_dir: Path, *, include_superseded: bool = False) -> list[dict]:
    """최신 경기부터. 읽을 수 없는 폴더는 건너뛴다. 새 기록으로 대체된 옛 게임(`supersededBy`)은 기본으로 뺀다."""
    try:
        folders = [p for p in games_dir.iterdir() if p.is_dir() and valid_key(p.name)]
    except OSError:
        return []
    games = []
    for folder in sorted(folders, key=lambda p: p.name, reverse=True):
        try:
            game = load_game(games_dir, folder.name)
        except GameNotFound:
            continue
        if include_superseded or not game.get("supersededBy"):
            games.append(game)
    return games


def has_full_video(games_dir: Path, key: str) -> bool:
    return (game_dir(games_dir, key) / FULL_VIDEO).is_file()


def update_game(games_dir: Path, key: str, change: Callable[[dict], None]) -> dict:
    """읽고 → `change(data)` 로 고치고 → 원자적으로 쓴다. 동시 요청이 서로의 수정을 덮지 않게 잠근다."""
    with _lock:
        data = load_game(games_dir, key)
        change(data)
        write_game_json(game_dir(games_dir, key), data)
        return data


def _probe_duration(video: Path) -> float | None:
    from lumia_briefing_room.config import discover_ffmpeg
    from lumia_briefing_room.video.vod import find_ffprobe, probe_video

    try:
        ffprobe = find_ffprobe(discover_ffmpeg())
        return probe_video(video, ffprobe_path=ffprobe).duration_sec if ffprobe else None
    except Exception:
        return None


def relink_restored_full_video(
    games_dir: Path, key: str, *, probe: Callable[[Path], float | None] = _probe_duration
) -> bool:
    """자동 정리로 지운 풀영상을 사용자가 휴지통에서 되살렸으면 `game.json` 을 다시 이어 준다."""
    video = game_dir(games_dir, key) / FULL_VIDEO
    try:
        game = load_game(games_dir, key)
        if not game.get("fullVideoDeletedAt") or not video.is_file():
            return False
        size = video.stat().st_size
    except (GameNotFound, OSError):
        return False
    old = game.get("deletedFullVideo")
    duration = old.get("durationSec") if isinstance(old, dict) else None
    if duration is None:
        duration = probe(video)
    if duration is None:
        return False

    def change(data: dict) -> None:
        data["fullVideo"] = {**(old if isinstance(old, dict) else {"path": FULL_VIDEO}), "sizeBytes": size, "durationSec": duration}
        data.pop("fullVideoDeletedAt", None)
        data.pop("deletedFullVideo", None)

    update_game(games_dir, key, change)
    return True
