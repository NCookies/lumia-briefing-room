from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from lumia_briefing_room.detect.pvp import PvpScore
from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.detect.types import CombatInterval
from lumia_briefing_room.pipeline.clip import ClipRange
from lumia_briefing_room.pipeline.metadata import (
    _teammate_names,
    match_result_dict,
    phase_index,
    revive_cost,
)
from lumia_briefing_room.video.vod import find_ffprobe, probe_video


@dataclass(frozen=True)
class VodCutResult:
    duration_sec: float


def vod_clip_id(vod: str, game_index: int, start_sec: float) -> str:
    return f"vod_{vod}_g{game_index:02d}_{int(start_sec):06d}"


def cut_vod_clip(
    vod_path: Path,
    clip_range: ClipRange,
    out_path: Path,
    *,
    ffmpeg_path: Path,
    include_audio: bool = True,
) -> VodCutResult:
    """다시보기 영상에서 구간을 재인코딩 없이 잘라낸다. 시작은 그 앞 키프레임(1초 간격)에 붙는다."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(ffmpeg_path), "-hide_banner", "-v", "error", "-y",
        "-ss", f"{clip_range.start:.3f}", "-i", str(vod_path),
        "-t", f"{clip_range.end - clip_range.start:.3f}",
        "-map", "0:v:0",
    ]
    if include_audio:
        cmd += ["-map", "0:a:0?"]
    cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero", str(out_path)]
    subprocess.run(cmd, check=True, capture_output=True)

    ffprobe_path = find_ffprobe(ffmpeg_path)
    duration = probe_video(out_path, ffprobe_path=ffprobe_path).duration_sec
    return VodCutResult(duration_sec=duration)


def build_vod_metadata(
    *,
    title: str,
    vod_id: str,
    vod_file: str,
    streamer: str | None,
    game_index: int,
    game_start: float,
    game_end: float,
    width: int,
    height: int,
    interval: CombatInterval,
    clip_range: ClipRange,
    duration_sec: float,
    thumbnail_path: str | None,
    pvp: PvpScore | None,
    match_kills: int | None,
    match_assists: int | None,
    match_result: ResultScreen | None,
    result_image_path: str | None,
    audio_status: str = "full",
) -> dict:
    """스팀 클립 메타데이터와 같은 필드 이름을 쓰되, 세션 필드 대신 다시보기 위치 필드를 채운다(SPEC §2.14)."""
    game_day = interval.game_day
    day_night = interval.day_night
    phase = phase_index(game_day, day_night) if game_day is not None and day_night is not None else None
    return {
        "title": title,
        "source": "vod",
        "vodId": vod_id,
        "vodFile": vod_file,
        "streamer": streamer,
        "vodGameIndex": game_index,
        "gameStartOffsetSec": game_start,
        "gameEndOffsetSec": game_end,
        "sourceWidth": width,
        "sourceHeight": height,
        "videoOffsetSec": clip_range.start,
        "durationSec": duration_sec,
        "thumbnailPath": thumbnail_path,
        "sourceIncomplete": False,
        "audioStatus": audio_status,
        "combatStartOffsetSec": interval.start,
        "combatEndOffsetSec": interval.end,
        "prerollSource": clip_range.preroll_source,
        "tags": sorted(interval.tags),
        "killDelta": interval.k_delta,
        "assistDelta": interval.a_delta,
        "died": interval.died,
        "pvpScore": pvp.score if pvp else 0.0,
        "pvpSignals": list(pvp.signals) if pvp else [],
        "teamWipe": None,
        "enemyRingMean": interval.enemy_ring_mean,
        "region": interval.region,
        "userLabel": None,
        "labelSource": None,
        "labelConflict": False,
        "gameDay": game_day,
        "dayNight": day_night,
        "phaseIndex": phase,
        "reviveCost": revive_cost(phase) if phase is not None else None,
        "myCharacter": match_result.character if match_result else None,
        "teamCharacters": _teammate_names(match_result),
        "pinned": False,
        "deletedAt": None,
        "matchKills": match_kills,
        "matchAssists": match_assists,
        "matchTeamKills": None,
        "detectorConfidence": interval.confidence,
        "matchResult": match_result_dict(match_result, result_image_path),
    }
