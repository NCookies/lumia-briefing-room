"""풀영상을 지우기 직전, 확실한 후보(킬·어시·사망) 중 아직 저장 안 된 것을 클립으로 남긴다. (`retention.preserveBeforeDelete`)

하나라도 남기지 못하면 실패로 알려 그 풀영상을 이번 정리에서 지우지 않게 한다(교전을 잃지 않는다).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from lumia_briefing_room.config import Config
from lumia_briefing_room.pipeline import game_candidates as gcand
from lumia_briefing_room.pipeline.game_clip_save import save_and_mark
from lumia_briefing_room.pipeline.game_files import GameNotFound, load_game

log = logging.getLogger(__name__)

Preserver = Callable[[Path], bool]


def candidates_to_preserve(game: dict) -> list[dict]:
    """무시하지 않았고 아직 저장하지 않은 확실한 후보."""
    return gcand.select_for_batch(game, "certain")


def preserve_candidates(folder: Path, game: dict, save_one: Callable[[dict, dict], object]) -> bool:
    """`save_one(game, cand)` 로 남길 후보를 모두 저장한다. 하나라도 실패하면 False."""
    for cand in candidates_to_preserve(game):
        try:
            save_one(game, cand)
        except Exception:
            log.exception("지우기 전 클립을 남기지 못했다: %s %s", folder.name, cand.get("id"))
            return False
    return True


def make_preserver(cfg: Config, ffmpeg_path: Path | None) -> Preserver:
    def preserve(folder: Path) -> bool:
        games_dir = folder.parent
        try:
            game = load_game(games_dir, folder.name)
        except GameNotFound:
            return False
        if not candidates_to_preserve(game):
            return True
        if ffmpeg_path is None:
            log.error("ffmpeg 를 찾을 수 없어 지우기 전 클립을 남기지 못했다: %s", folder.name)
            return False
        return preserve_candidates(
            folder, game,
            lambda g, cand: save_and_mark(games_dir, folder.name, g, cand, cfg=cfg, ffmpeg_path=ffmpeg_path),
        )

    return preserve
