"""후보 하나를 풀영상에서 클립으로 저장하고 `game.json` 에 저장 사실을 남긴다. (게임 API 와 자동 정리 직전 보존이 함께 쓴다)"""

from __future__ import annotations

from pathlib import Path

from lumia_briefing_room.config import Config, resolve_paths
from lumia_briefing_room.pipeline import game_candidates as gcand
from lumia_briefing_room.pipeline.clip_from_full import save_candidate_clip
from lumia_briefing_room.pipeline.game_files import game_dir, update_game


def clip_dirs_for(game: dict, cfg: Config) -> tuple[Path, Path]:
    """(정보 폴더, 새 영상이 놓일 폴더). 영상 파일 게임에서 저장한 클립은 스팀 클립과 섞이지 않게 영상 클립 자리에 둔다."""
    resolved = resolve_paths(cfg.paths)
    if game.get("source") == "vod":
        return resolved.library_vod, resolved.clips_vod
    return resolved.library_steam, resolved.clips_steam


def save_and_mark(games_dir: Path, key: str, game: dict, cand: dict, *, cfg: Config, ffmpeg_path: Path) -> str:
    """이미 저장했고 범위가 그대로면 다시 자르지 않고 기존 클립 ID 를 돌려준다."""
    duration = float((game.get("fullVideo") or {}).get("durationSec") or 0.0)
    existing = (cand.get("user") or {}).get("savedClipId")
    if existing and not gcand.range_changed(cand, duration):
        return existing
    used = gcand.effective_range(cand, duration)
    meta_dir, video_dir = clip_dirs_for(game, cfg)
    clip_id = save_candidate_clip(
        game, cand, game_folder=game_dir(games_dir, key), clips_dir=meta_dir, cfg=cfg, ffmpeg_path=ffmpeg_path,
        replace_clip_id=existing, video_dir=video_dir, video_roots=resolve_paths(cfg.paths).clip_roots,
    )

    def mark(data: dict) -> None:
        found = gcand.find_candidate(data, cand["id"])
        found["user"] = {
            **(found.get("user") or {}),
            "savedClipId": clip_id,
            "savedStart": round(used[0], 3),
            "savedEnd": round(used[1], 3),
        }

    update_game(games_dir, key, mark)
    return clip_id
