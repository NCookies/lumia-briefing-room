"""다시 분석 뒤 클립 정리: 사용자가 보관한 클립만 두고 자동 저장된 클립은 지운 다음, 저장 방식이 auto 면 새 후보에서 다시 뽑는다.

자동 저장 = `자동 보관` 카테고리에 있는 클립(`game_routes.self_saved_category` 의 `archived=False`). 옛 경로 모드처럼 카테고리가 없으면 구분할 수 없어 모두 보관한 것으로 본다.
새 결과가 확정된 뒤에만 지우므로 다시 분석이 실패하면 기존 클립은 그대로다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection
from pathlib import Path

from lumia_briefing_room.config import Config
from lumia_briefing_room.pipeline import game_candidates as gcand
from lumia_briefing_room.pipeline.game_clip_save import save_and_mark
from lumia_briefing_room.pipeline.game_files import load_game

log = logging.getLogger(__name__)


def auto_saved_clip_ids(game: dict, *, is_auto: Callable[[str], bool]) -> set[str]:
    """자동 후보에 연결된 클립 중 자동 저장된 것(직접 추가한 구간의 클립은 사용자가 만든 것이라 뺀다)."""
    found = ((c.get("user") or {}).get("savedClipId") for c in game.get("candidates") or [])
    return {clip_id for clip_id in found if clip_id and is_auto(clip_id)}


def refresh_auto_clips(
    games_dir: Path, key: str, auto_ids: Collection[str], *, cfg: Config, ffmpeg_path: Path,
    delete: Callable[[str], object], save: Callable = save_and_mark,
) -> tuple[int, int]:
    """(새로 만든 클립 수, 만들지 못한 수). 자동 저장 클립을 지우고, `clip.saveMode=auto` 면 보관되지 않은 후보를 풀영상에서 다시 뽑는다."""
    for clip_id in auto_ids:
        try:
            delete(clip_id)
        except Exception:
            log.exception("자동 저장 클립을 지우지 못했다: %s", clip_id)
    if cfg.clip.save_mode != "auto":
        return 0, 0
    game = load_game(games_dir, key)
    made = failed = 0
    for cand in gcand.select_for_batch(game, "all"):
        try:
            save(games_dir, key, load_game(games_dir, key), cand, cfg=cfg, ffmpeg_path=ffmpeg_path, manual=False)
            made += 1
        except Exception:
            log.exception("클립을 다시 뽑지 못했다: %s %s", key, cand["id"])
            failed += 1
    return made, failed
