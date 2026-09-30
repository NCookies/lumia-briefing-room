"""이미 저장된 게임의 결과 화면을 풀영상 끝부분으로 다시 읽어 채운다. (plan §2-5)

결과가 없거나(`matchResult` 없음) 일반/랭크를 못 읽었거나(`unknown`) 순위가 빈 게임이 대상이다. 사용자가 직접 고친 게임
(`matchResultSource="manual"`)은 `force` 여도 건드리지 않는다.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.pipeline.clip_assets import stored_asset_path
from lumia_briefing_room.pipeline.game_files import list_games, update_game
from lumia_briefing_room.pipeline.game_store import FULL_VIDEO
from lumia_briefing_room.pipeline.metadata import match_result_dict
from lumia_briefing_room.pipeline.result_scan import result_image_name, save_result_image

log = logging.getLogger(__name__)

COBALT_OUTCOMES = ("승리", "패배")
_EMPTY = (None, "", "unknown")


@dataclass
class BackfillReport:
    filled: int = 0
    skipped: int = 0
    locked: int = 0
    no_video: int = 0
    not_found: int = 0
    failed: int = 0


def needs_result(game: dict) -> bool:
    result = game.get("matchResult")
    if not result:
        return True
    if result.get("outcome") in COBALT_OUTCOMES:
        return False
    return result.get("matchType") in _EMPTY or result.get("placement") is None


def _clip_metas(clips_dir: Path, game: dict) -> list[tuple[Path, dict]]:
    found = []
    for path in sorted(clips_dir.glob("*.json")) if clips_dir.is_dir() else []:
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            isinstance(meta, dict)
            and meta.get("matchStartUtc") == game.get("matchStartUtc")
            and meta.get("sessionDir") == game.get("sessionDir")
        ):
            found.append((path, meta))
    return found


def _merge(old: dict | None, new: dict) -> dict:
    """새로 읽은 값이 비면(None, 빈 문자열, unknown) 예전 값을 남긴다."""
    merged = dict(new)
    for key, value in (old or {}).items():
        if key != "imagePath" and merged.get(key) in _EMPTY and value not in _EMPTY:
            merged[key] = value
    return merged


def backfill_game_results(
    games_dir: Path,
    clips_dir: Path,
    *,
    find: Callable[[Path], ResultScreen | None],
    keys: Iterable[str] | None = None,
    force: bool = False,
    thumbnails_dir: Path | None = None,
    on_game: Callable[[str, str], None] | None = None,
) -> BackfillReport:
    report = BackfillReport()
    wanted = set(keys) if keys is not None else None
    thumbnails_dir = thumbnails_dir or clips_dir / ".thumbs"

    def note(key: str, text: str) -> None:
        if on_game is not None:
            on_game(key, text)

    for game in list_games(games_dir):
        key = game["gameKey"]
        if wanted is not None and key not in wanted:
            continue
        clips = _clip_metas(clips_dir, game)
        if game.get("matchResultSource") == "manual" or any(m.get("matchResultSource") == "manual" for _, m in clips):
            report.locked += 1
            note(key, "수동으로 고친 게임이라 건너뜀")
            continue
        if game.get("gameMode") == "cobalt" or (not force and not needs_result(game)):
            report.skipped += 1
            continue
        video = games_dir / key / FULL_VIDEO
        if not video.is_file():
            report.no_video += 1
            note(key, "풀영상이 없어 건너뜀")
            continue
        try:
            result = find(video)
        except Exception:
            log.exception("게임 %s 결과 화면 판독 실패", key)
            report.failed += 1
            note(key, "판독 실패")
            continue
        if result is None:
            report.not_found += 1
            note(key, "결과 화면을 못 찾음")
            continue

        image_rel = None
        if result.image is not None:
            save_result_image(result.image, games_dir / key / "result.jpg")
            image_rel = "result.jpg"

        def change(data: dict) -> None:
            data["matchResult"] = _merge(data.get("matchResult"), match_result_dict(result, image_rel) or {})
            if image_rel is None and (data["matchResult"] or {}).get("imagePath") is None:
                data["matchResult"].pop("imagePath", None)

        update_game(games_dir, key, change)

        if clips:
            start = datetime.fromisoformat(game["matchStartUtc"].replace("Z", "+00:00"))
            clip_image = None
            if result.image is not None:
                image_path = thumbnails_dir / result_image_name(start)
                save_result_image(result.image, image_path)
                clip_image = stored_asset_path(image_path, clips_dir)
            for path, _ in clips:
                meta = json.loads(path.read_text(encoding="utf-8"))
                meta["matchResult"] = _merge(meta.get("matchResult"), match_result_dict(result, clip_image) or {})
                path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        report.filled += 1
        note(key, f"{result.match_type} · 순위 {result.placement if result.placement is not None else '없음'}")
    return report
