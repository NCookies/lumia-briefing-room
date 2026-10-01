"""풀영상 전환 전에 분석한 영상 파일 게임을 `games/vod_<영상id>_g<번호>/game.json` 으로 옮긴다. (plan-fullvideo.md §3.7, F6)

스팀 쪽 `legacy_games` 와 같은 역할이다: 게임(영상 색인의 `games[]`)의 클립들을 후보(저장됨)로 묶고 결과·초상화·결과표 이미지를
게임 폴더로 복사한다. 풀영상은 없다(`fullVideo` 없음, `legacy` 표시). 몇 번 돌려도 같고, 옛 클립·색인은 지우지 않으며,
`game.json` 이 이미 있는 게임과 풀영상을 자르는 중인 폴더는 건드리지 않는다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from lumia_briefing_room.pipeline.clip_assets import resolve_character_portrait, resolve_result_image
from lumia_briefing_room.pipeline import deleted_games
from lumia_briefing_room.pipeline.game_store import FULL_VIDEO, GAME_JSON, SCHEMA_VERSION, vod_game_key, write_game_json
from lumia_briefing_room.pipeline.legacy_games import LEGACY_ERROR, _candidate, _copy, _read

log = logging.getLogger(__name__)

_PORTRAIT_SLOTS = ("me", "teammate1", "teammate2")
INDEX_DIRNAME = ".vods"


def _indexes(vod_clips: Path) -> list[dict]:
    folder = vod_clips / INDEX_DIRNAME
    indexes = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        data = _read(path)
        if data is not None and data.get("id") and isinstance(data.get("games"), list):
            indexes.append(data)
    return indexes


def _clip_metas(vod_clips: Path, game: dict) -> list[tuple[str, Path, dict]]:
    metas = []
    for clip_id in game.get("clipIds") or []:
        path = vod_clips / f"{clip_id}.json"
        meta = _read(path)
        if meta is not None:
            metas.append((clip_id, path, meta))
    return metas


def _build(folder: Path, vod_clips: Path, index: dict, game: dict) -> dict:
    clips = _clip_metas(vod_clips, game)
    result = game.get("result") if isinstance(game.get("result"), dict) else None
    kept = None
    if result is not None:
        kept = {k: v for k, v in result.items() if k != "imagePath"}
        image = None
        for _, path, meta in clips:
            image = resolve_result_image(path, meta)
            if image is not None and image.is_file():
                break
        if (image is None or not image.is_file()) and result.get("imagePath"):
            image = vod_clips / result["imagePath"]
        copied = _copy(image, folder / "result.jpg")
        if copied:
            kept["imagePath"] = copied

    portraits: dict[str, str | None] = {}
    for slot in _PORTRAIT_SLOTS:
        portraits[slot] = next(
            (
                name for _, path, meta in clips
                if (name := _copy(resolve_character_portrait(path, meta, slot), folder / f"portrait_{slot}.jpg"))
            ),
            None,
        )

    start = float(game.get("startSec") or 0.0)
    candidates = [_candidate(clip_id, meta, start) for clip_id, _, meta in clips]
    candidates.sort(key=lambda c: (c["start"], c["id"]))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "gameKey": vod_game_key(index["id"], int(game["index"])),
        "source": "vod",
        "legacy": True,
        "vodId": index["id"],
        "vodFile": index.get("path"),
        "streamer": index.get("streamer"),
        "vodGameIndex": int(game["index"]),
        "vodStartSec": None,
        "vodEndSec": None,
        "spanStartSec": game.get("startSec"),
        "spanEndSec": game.get("endSec"),
        "matchStartUtc": None,
        "matchEndUtc": None,
        "gameMode": game.get("gameMode"),
        "sourceWidth": index.get("width"),
        "sourceHeight": index.get("height"),
        "sourceIncomplete": False,
        "matchKills": game.get("kFinal"),
        "matchAssists": game.get("aFinal"),
        "matchResult": kept,
        "portraits": portraits,
        "saveMode": "auto",
        "fullVideo": None,
        "fullVideoError": LEGACY_ERROR,
        "candidates": candidates,
        "userCandidates": [],
        "markers": [],
        "pinned": any(bool(m.get("pinned")) for _, _, m in clips),
    }


def migrate_legacy_vod_games(vod_clips: Path, games_dir: Path) -> list[str]:
    """새로 만든 게임 키 목록. 이미 옮긴 게임은 다시 만들지 않으므로 두 번째부터는 빈 목록이다."""
    created: list[str] = []
    deleted = deleted_games.load(games_dir)
    for index in _indexes(vod_clips):
        for game in index["games"]:
            if not isinstance(game, dict) or "index" not in game:
                continue
            key = vod_game_key(index["id"], int(game["index"]))
            folder = games_dir / key
            if key in deleted or (folder / GAME_JSON).exists() or (folder / FULL_VIDEO).exists():
                continue
            try:
                folder.mkdir(parents=True, exist_ok=True)
                write_game_json(folder, _build(folder, vod_clips, index, game))
            except OSError:
                log.exception("이전 버전 영상 게임 %s 를 옮기지 못했다", key)
                continue
            created.append(key)
    return created
