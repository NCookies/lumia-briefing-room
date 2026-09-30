"""게임 하나 = `games/<경기키>/` 폴더 하나. 풀영상(`full.mp4`)과 게임 기록(`game.json`). (plan-fullvideo.md §3.1)"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from lumia_briefing_room.detect.types import CombatInterval

GAME_JSON = "game.json"
FULL_VIDEO = "full.mp4"
SCHEMA_VERSION = 1
CERTAIN_TAGS = frozenset({"kill", "assist", "death"})

T = TypeVar("T")


def game_key(match_start: datetime) -> str:
    return f"{match_start:%Y%m%d_%H%M%S}"


def vod_game_key(vod_id: str, index: int) -> str:
    """영상 파일 게임의 키. 영상 게임은 실제 시각이 없어 시작 시각 키를 못 쓴다.

    vodId(파일 내용 해시)라 영상끼리 겹치지 않고, 게임 번호는 영상 안에서 유일하다. 기존 영상 클립 ID
    (`vod_<vodId>_g01_<초>`)와 앞부분이 같아 옛 클립과 게임이 이어지고, 스팀 키(`YYYYMMDD_HHMMSS`)와는 모양이 달라 섞이지 않는다.
    """
    return f"vod_{vod_id}_g{index:02d}"


def is_certain(tags: frozenset[str] | set[str]) -> bool:
    """킬·어시스트·사망이 있는 후보. 풀영상을 못 만들 때도 클립으로는 남긴다."""
    return bool(CERTAIN_TAGS & set(tags))


def plans_to_save(
    plans: Sequence[T], save_mode: str, full_video_ok: bool, *, is_certain: Callable[[T], bool]
) -> list[T]:
    """풀영상이 없으면 저장 옵션과 무관하게 확실한 후보만 클립으로 남긴다(교전을 영구히 잃지 않는다, plan §3.4)."""
    if not full_video_ok:
        return [p for p in plans if is_certain(p)]
    if save_mode == "manual":
        return []
    return list(plans)


def has_room(*, free_bytes: int, needed_bytes: int, margin_bytes: int) -> bool:
    return free_bytes > needed_bytes + margin_bytes


def _rel(t: float, offset_sec: float) -> float:
    return round(max(0.0, t - offset_sec), 3)


def candidate_dict(
    candidate_id: str,
    *,
    interval: CombatInterval,
    start: float,
    end: float,
    preroll_source: str,
    title: str,
    offset_sec: float,
    pvp_score: float,
    pvp_signals: list[str],
    clip_id: str | None,
) -> dict:
    """시각은 모두 풀영상 기준 초다(`offset_sec` = 풀영상 첫 세그먼트의 세션 기준 시각)."""
    return {
        "id": candidate_id,
        "start": _rel(start, offset_sec),
        "end": _rel(end, offset_sec),
        "combatStart": _rel(interval.start, offset_sec),
        "combatEnd": _rel(interval.end, offset_sec),
        "prerollSource": preroll_source,
        "title": title,
        "tags": sorted(interval.tags),
        "certain": is_certain(interval.tags),
        "killDelta": interval.k_delta,
        "assistDelta": interval.a_delta,
        "died": interval.died,
        "pvpScore": pvp_score,
        "pvpSignals": list(pvp_signals),
        "enemyRingMean": interval.enemy_ring_mean,
        "ultimateDelta": interval.ultimate_delta,
        "region": interval.region,
        "gameDay": interval.game_day,
        "dayNight": interval.day_night,
        "cobaltPhase": interval.cobalt_phase,
        "detectorConfidence": interval.confidence,
        "user": {"savedClipId": clip_id} if clip_id else {},
    }


def markers_dict(markers: Sequence[tuple[float, str]], *, offset_sec: float) -> list[dict]:
    return [{"t": _rel(t, offset_sec), "kind": kind} for t, kind in sorted(markers)]


def write_game_json(folder: Path, data: dict) -> Path:
    """임시 파일에 쓴 뒤 바꿔치기한다. game.json 이 있어야 게임이 목록에 보이므로 마지막에 쓴다."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / GAME_JSON
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path
