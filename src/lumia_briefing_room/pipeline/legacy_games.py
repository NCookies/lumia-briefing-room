"""풀영상 전환 전에 만든 클립·게임 기록(`.games`)을 `games/<경기키>/game.json` 으로 옮긴다. (plan-fullvideo.md §3.6-d, F4-c)

게임 하나(sessionDir+matchStartUtc)의 클립들을 후보(저장됨)로 묶고 결과·초상화·결과표 이미지를 게임 폴더로 복사한다.
풀영상은 없다(`fullVideo` 없음, `legacy` 표시). 몇 번 돌려도 같고, 옛 파일은 지우지 않고, `game.json` 이 이미 있는 경기와
풀영상을 자르는 중인 폴더는 건드리지 않는다.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lumia_briefing_room.pipeline import deleted_games
from lumia_briefing_room.pipeline.clip_assets import resolve_character_portrait, resolve_result_image
from lumia_briefing_room.pipeline.game_files import list_games, update_game
from lumia_briefing_room.pipeline.game_store import FULL_VIDEO, GAME_JSON, SCHEMA_VERSION, game_key, is_certain, write_game_json
from lumia_briefing_room.pipeline.game_records import RECORDS_DIRNAME

log = logging.getLogger(__name__)

LEGACY_ERROR = "이전 버전에서 분석한 게임이라 풀영상이 없습니다"
_PORTRAIT_SLOTS = ("me", "teammate1", "teammate2")


def _parse_utc(text: object) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _copy(src: Path | None, dest: Path) -> str | None:
    if src is None or not src.is_file():
        return None
    try:
        shutil.copyfile(src, dest)
    except OSError:
        return None
    return dest.name


def _candidate(clip_id: str, meta: dict, offset_sec: float) -> dict:
    def rel(value: object) -> float:
        return round(max(0.0, float(value or 0.0) - offset_sec), 3)

    start = rel(meta.get("videoOffsetSec"))
    tags = sorted(meta.get("tags") or [])
    return {
        "id": clip_id,
        "start": start,
        "end": round(start + float(meta.get("durationSec") or 0.0), 3),
        "combatStart": rel(meta.get("combatStartOffsetSec")),
        "combatEnd": rel(meta.get("combatEndOffsetSec")),
        "prerollSource": meta.get("prerollSource"),
        "title": meta.get("title") or clip_id,
        "tags": tags,
        "certain": is_certain(tags),
        "killDelta": meta.get("killDelta") or 0,
        "assistDelta": meta.get("assistDelta") or 0,
        "died": bool(meta.get("died")),
        "pvpScore": meta.get("pvpScore") or 0.0,
        "pvpSignals": list(meta.get("pvpSignals") or []),
        "enemyRingMean": meta.get("enemyRingMean"),
        "ultimateDelta": meta.get("ultimateDelta"),
        "region": meta.get("region"),
        "gameDay": meta.get("gameDay"),
        "dayNight": meta.get("dayNight"),
        "cobaltPhase": meta.get("cobaltPhase"),
        "detectorConfidence": meta.get("detectorConfidence"),
        "user": {"savedClipId": clip_id},
    }


def _collect(clips_dir: Path) -> dict[tuple[str, str], dict]:
    """게임별로 {"clips": [(id, meta_path, meta)], "record": dict|None, "record_dir": Path}."""
    groups: dict[tuple[str, str], dict] = {}

    def group(meta: dict) -> dict | None:
        start = _parse_utc(meta.get("matchStartUtc"))
        if start is None:
            return None
        key = (str(meta.get("sessionDir") or ""), game_key(start))
        return groups.setdefault(key, {"clips": [], "record": None, "record_dir": None, "start": start})

    for path in sorted(clips_dir.glob("*.json")):
        meta = _read(path)
        target = group(meta) if meta is not None else None
        if target is not None:
            target["clips"].append((path.stem, path, meta))

    records = clips_dir / RECORDS_DIRNAME
    for path in sorted(records.glob("*.json")) if records.is_dir() else []:
        meta = _read(path)
        target = group(meta) if meta is not None else None
        if target is not None:
            target["record"], target["record_dir"] = meta, records
    return groups


def _build(folder: Path, clips_dir: Path, info: dict) -> dict:
    clips = info["clips"]
    record = info["record"] or {}
    first_meta = clips[0][2] if clips else record
    result = next((m.get("matchResult") for _, _, m in clips if isinstance(m.get("matchResult"), dict)), None)
    if result is None and isinstance(record.get("matchResult"), dict):
        result = record["matchResult"]

    image = None
    for _, path, meta in clips:
        image = resolve_result_image(path, meta)
        if image is not None and image.is_file():
            break
    if (image is None or not image.is_file()) and result is not None and result.get("imagePath"):
        raw = Path(result["imagePath"])
        image = raw if raw.is_absolute() else (info["record_dir"] or clips_dir) / raw
    kept = None
    if result is not None:
        kept = {k: v for k, v in result.items() if k != "imagePath"}
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

    session_start = _parse_utc(first_meta.get("sessionStartUtc"))
    offset = (info["start"] - session_start).total_seconds() if session_start else 0.0
    candidates = [_candidate(clip_id, meta, offset) for clip_id, _, meta in clips]
    candidates.sort(key=lambda c: (c["start"], c["id"]))

    return {
        "schemaVersion": SCHEMA_VERSION,
        "gameKey": game_key(info["start"]),
        "source": "steam",
        "legacy": True,
        "sessionDir": first_meta.get("sessionDir"),
        "sessionStartUtc": first_meta.get("sessionStartUtc"),
        "matchStartUtc": first_meta.get("matchStartUtc"),
        "matchEndUtc": first_meta.get("matchEndUtc"),
        "gameMode": first_meta.get("gameMode"),
        "sourceWidth": first_meta.get("sourceWidth"),
        "sourceHeight": first_meta.get("sourceHeight"),
        "sourceIncomplete": bool(first_meta.get("sourceIncomplete")),
        "matchKills": first_meta.get("matchKills"),
        "matchAssists": first_meta.get("matchAssists"),
        "matchResult": kept,
        "matchResultSource": "manual" if kept is not None and any(m.get("matchResultSource") == "manual" for _, _, m in clips) else None,
        "portraits": portraits,
        "saveMode": "auto",
        "fullVideo": None,
        "fullVideoError": LEGACY_ERROR,
        "candidates": candidates,
        "userCandidates": [],
        "markers": [],
        "pinned": any(bool(m.get("pinned")) for _, _, m in clips),
    }


def migrate_legacy_games(clips_dir: Path, games_dir: Path) -> list[str]:
    """새로 만든 게임 키 목록. 이미 옮긴 경기는 다시 만들지 않으므로 두 번째부터는 빈 목록이다."""
    if not clips_dir.is_dir():
        return []
    created: list[str] = []
    deleted = deleted_games.load(games_dir)
    for (_, key), info in sorted(_collect(clips_dir).items()):
        folder = games_dir / key
        if key in deleted or (folder / GAME_JSON).exists() or (folder / FULL_VIDEO).exists():
            continue
        try:
            folder.mkdir(parents=True, exist_ok=True)
            write_game_json(folder, _build(folder, clips_dir, info))
        except OSError:
            log.exception("이전 버전 게임 %s 를 옮기지 못했다", key)
            continue
        created.append(key)
    return created


def find_legacy_game(
    games_dir: Path, window_start: datetime, window_end: datetime | None = None, tolerance_sec: float = 240.0
) -> dict | None:
    """이 구간에서 시작한, 풀영상이 없는 옛 게임의 기록. 없으면 None."""
    lo = window_start - timedelta(seconds=tolerance_sec)
    hi = window_end if window_end is not None else window_start + timedelta(seconds=tolerance_sec)
    for game in list_games(games_dir):
        start = _parse_utc(game.get("matchStartUtc"))
        if start is not None and lo <= start <= hi and not game.get("fullVideo") and not game.get("fullVideoDeletedAt"):
            return game
    return None


def saved_clip_ids(game: dict, clips_dir: Path) -> set[str]:
    """옛 게임이 저장해 둔 클립 중 파일이 아직 있는 것."""
    return {
        clip_id
        for cand in game.get("candidates") or []
        if (clip_id := (cand.get("user") or {}).get("savedClipId")) and (clips_dir / f"{clip_id}.json").is_file()
    }


def existing_clip_ids(
    games_dir: Path, clips_dir: Path, window_start: datetime, window_end: datetime | None = None, tolerance_sec: float = 240.0
) -> set[str] | None:
    """이 구간에서 시작한 옛 게임이 이미 저장해 둔 클립 ID(파일이 아직 있는 것만). 그런 게임이 없으면 None.

    풀영상을 새로 만들 때 클립을 두 번 만들지 않는 기준이다.
    """
    game = find_legacy_game(games_dir, window_start, window_end, tolerance_sec)
    return None if game is None else saved_clip_ids(game, clips_dir)


def _session_span(game: dict, cand: dict, *, use_combat: bool = True) -> tuple[float, float]:
    """후보의 전투 구간을 세션 기준 초로. 옛 게임은 게임 시작 - 세션 시작, 새 게임은 풀영상 `offsetSec` 를 더한다."""
    start, end = cand.get("combatStart"), cand.get("combatEnd")
    if not use_combat or start is None or end is None:
        start, end = cand.get("start", 0.0), cand.get("end", 0.0)
    base = (game.get("fullVideo") or {}).get("offsetSec")
    if base is None:
        match, session = _parse_utc(game.get("matchStartUtc")), _parse_utc(game.get("sessionStartUtc"))
        base = (match - session).total_seconds() if match and session else 0.0
    return float(start) + float(base), float(end) + float(base)


def adopt_legacy_clips(games_dir: Path, legacy: dict, new_key: str) -> None:
    """풀영상을 새로 만든 게임(`new_key`)의 후보에, 겹치는 옛 클립을 저장됨으로 이어 준다(후보 하나에 클립 하나).

    새 게임의 시작이 옛 게임과 달라 키가 다르면(캐릭터 선택 확장 등) 옛 게임 기록은 `supersededBy` 로 대체 표시해 목록에서 뺀다.
    표시만 하고 지우지 않으므로 옛 클립에서 다시 게임을 만들지 않는다(`migrate_legacy_games` 가 폴더 존재로 건너뛴다).
    """
    old = [
        (cand["user"]["savedClipId"], _session_span(legacy, cand))
        for cand in legacy.get("candidates") or []
        if (cand.get("user") or {}).get("savedClipId")
    ]

    def link(data: dict) -> None:
        free = dict(old)
        for cand in data.get("candidates") or []:
            if (cand.get("user") or {}).get("savedClipId"):
                free.pop(cand["user"]["savedClipId"], None)
        for cand in data.get("candidates") or []:
            if (cand.get("user") or {}).get("savedClipId"):
                continue
            lo, hi = _session_span(data, cand)
            best = max(
                ((min(hi, e) - max(lo, s), clip_id) for clip_id, (s, e) in free.items()), default=(0.0, None),
            )
            if best[1] is not None and best[0] > 0:
                cand["user"] = {**(cand.get("user") or {}), "savedClipId": best[1]}
                free.pop(best[1])

    update_game(games_dir, new_key, link)
    if legacy["gameKey"] != new_key:
        update_game(games_dir, legacy["gameKey"], lambda d: d.update(supersededBy=new_key))
