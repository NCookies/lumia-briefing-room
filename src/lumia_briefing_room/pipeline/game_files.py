"""`games/<경기키>/game.json` 읽기·수정. API 와 클립 저장이 함께 쓴다. (plan-fullvideo.md §3.1)"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from pathlib import Path

from lumia_briefing_room.pipeline.game_store import FULL_VIDEO, GAME_JSON, write_game_json

_KEY = re.compile(r"^\d{8}_\d{6}$")
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
