"""영상 파일(다시보기) 게임의 풀영상·게임 기록. (plan-fullvideo.md §3.7, §3.8)

영상 한 편에서 게임마다 캐릭터 선택 화면 ~ 결과 화면 끝을 `-c copy` 로 잘라 `games/<게임 키>/full.mp4` 로 저장하고,
후보·마커·결과·초상화를 `game.json` 에 남긴다. 스팀 게임과 같은 형식이라 같은 화면(GameViewer)이 그대로 연다.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from lumia_briefing_room.config import Config
from lumia_briefing_room.detect.pvp import score_interval
from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.detect.types import MatchDetection, PortraitCrops
from lumia_briefing_room.pipeline.clip import ClipRange
from lumia_briefing_room.pipeline.delete_helper import PERMANENT, permanently_delete, send_to_recycle_bin
from lumia_briefing_room.pipeline.ffmpeg_errors import describe_clip_error
from lumia_briefing_room.pipeline.game_store import (
    FULL_VIDEO,
    SCHEMA_VERSION,
    candidate_dict,
    has_room,
    markers_dict,
    vod_game_key,
    write_game_json,
)
from lumia_briefing_room.pipeline.metadata import match_result_dict
from lumia_briefing_room.pipeline.portrait_scan import PORTRAIT_SLOTS, save_portrait_image
from lumia_briefing_room.pipeline.result_scan import save_result_image
from lumia_briefing_room.pipeline.orchestrator import ClipPlan, NamedCandidate, _aggregate_interval, default_title, next_phase_clip_index
from lumia_briefing_room.pipeline.vod_clips import cut_vod_clip, vod_clip_id
from lumia_briefing_room.pipeline.vod_games import GameSpan

log = logging.getLogger(__name__)

# 영상에는 "로비로 나가는 순간"을 알려 주는 신호가 없다. 결과 화면이 처음 읽힌 뒤 이 시간까지를 결과 화면으로 본다(결과 화면 3장 다수결 + 머무는 시간).
RESULT_DWELL_SEC = 15.0
# 결과 화면을 안 보고 넘긴 게임: 마지막 인게임 프레임 뒤로 이만큼만 붙인다.
NO_RESULT_TAIL_SEC = 10.0
# 캐릭터 선택 화면을 못 찾은 게임(방송 화면 전환으로 가려짐 등): 첫 인게임 프레임 앞으로 이만큼 붙인다.
NO_SELECT_LEAD_SEC = 10.0
MARGIN_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class VodSource:
    vod_id: str
    path: Path
    streamer: str | None
    width: int
    height: int
    duration_sec: float
    size_bytes: int


@dataclass(frozen=True)
class VodFullVideo:
    size_bytes: int | None
    duration_sec: float


@dataclass(frozen=True)
class VodFullOutcome:
    video: VodFullVideo | None
    error: str | None = None


def effective_start(span: GameSpan) -> float:
    return span.select_start if span.select_start is not None else max(0.0, span.start - NO_SELECT_LEAD_SEC)


def vod_game_range(
    span: GameSpan, *, result_at: float | None, prev_end: float | None, next_start: float | None, duration: float
) -> tuple[float, float]:
    """풀영상으로 자를 원본 영상 안 구간 (시작, 끝). 시작은 선택 화면, 끝은 결과 화면이 끝날 무렵이다.

    이웃 게임과 겹치지 않고(앞 게임 끝 뒤, 다음 게임 시작 앞) 영상 밖으로 나가지 않으며 마지막 인게임 프레임 앞에서 끝나지 않는다.
    """
    start = max(0.0, effective_start(span), prev_end or 0.0)
    end = result_at + RESULT_DWELL_SEC if result_at is not None else span.end + NO_RESULT_TAIL_SEC
    end = max(end, span.end)
    if next_start is not None:
        end = min(end, max(next_start, span.end))
    return start, min(end, duration)


def name_vod_candidates(
    plans: list[ClipPlan], vod_id: str, game_index: int, *, duration: float
) -> list[NamedCandidate]:
    """후보 ID = 클립 ID = 예전 분석이 만들던 클립 ID(`vod_<vodId>_g01_<시작 초>`)다. 같은 계획이면 옛 클립이 그대로 저장됨으로 이어진다."""
    named: list[NamedCandidate] = []
    phase_counts: dict[int | None, int] = {}
    for plan in plans:
        aggregated = _aggregate_interval(plan.intervals)
        rng = ClipRange(
            start=max(0.0, plan.range.start), end=min(duration, plan.range.end), preroll_source=plan.range.preroll_source
        )
        clip_id = vod_clip_id(vod_id, game_index, rng.start)
        title = default_title(
            aggregated.day_night, aggregated.region, aggregated.game_day,
            cobalt_phase=aggregated.cobalt_phase, clip_index=next_phase_clip_index(phase_counts, aggregated.cobalt_phase),
        )
        named.append(NamedCandidate(clip_id, clip_id, title, ClipPlan(range=rng, intervals=plan.intervals), aggregated))
    return named


def _free_bytes(folder: Path) -> int:
    probe = folder
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def cut_vod_full_video(
    video_path: Path,
    start: float,
    end: float,
    folder: Path,
    *,
    ffmpeg_path: Path,
    include_audio: bool,
    source_size: int,
    source_duration: float,
) -> VodFullOutcome:
    """원본에서 [start, end] 를 `-c copy` 로 `folder/full.mp4` 에 만든다. 실패해도 예외를 올리지 않는다(후보 기록·클립은 계속돼야 한다)."""
    needed = int(source_size * (end - start) / source_duration) if source_duration else 0
    try:
        free = _free_bytes(folder)
    except OSError as exc:
        return VodFullOutcome(None, f"저장 위치를 확인할 수 없습니다: {exc}")
    if not has_room(free_bytes=free, needed_bytes=needed, margin_bytes=MARGIN_BYTES):
        return VodFullOutcome(
            None, f"저장 공간이 부족해 풀영상을 만들지 못했습니다 (필요 약 {needed / 2**30:.1f}GB, 여유 {free / 2**30:.1f}GB)."
        )
    folder.mkdir(parents=True, exist_ok=True)
    tmp_out, final = folder / "full.tmp.mp4", folder / FULL_VIDEO
    try:
        cut = cut_vod_clip(
            video_path, ClipRange(start=start, end=end, preroll_source="combat"), tmp_out,
            ffmpeg_path=ffmpeg_path, include_audio=include_audio,
        )
        os.replace(tmp_out, final)
    except (OSError, subprocess.CalledProcessError, RuntimeError, ValueError, KeyError) as exc:
        tmp_out.unlink(missing_ok=True)
        message = describe_clip_error(exc)
        log.warning("영상 게임 풀영상 컷 실패 - 후보 기록과 클립 저장은 계속한다: %s", message)
        return VodFullOutcome(None, message)
    try:
        size = final.stat().st_size
    except OSError:
        size = None
    return VodFullOutcome(VodFullVideo(size_bytes=size, duration_sec=cut.duration_sec))


def vod_game_dict(
    *,
    source: VodSource,
    span: GameSpan,
    game_mode: str,
    detection: MatchDetection,
    candidates: list[NamedCandidate],
    saved_ids: dict[str, str],
    full_start: float,
    full_end: float,
    full: VodFullVideo | None,
    error: str | None,
    result: ResultScreen | None,
    result_file: str | None,
    portraits: dict[str, str | None],
    save_mode: str,
    cfg: Config,
) -> dict:
    """`game.json`. 후보·마커 시각은 풀영상 기준 초(0 = 원본 영상 안 `vodStartSec`)다."""
    rows = []
    for c in candidates:
        pvp = score_interval(c.aggregated, cfg.filter.pvp_weights)
        rows.append(candidate_dict(
            c.candidate_id, interval=c.aggregated, start=c.plan.range.start, end=c.plan.range.end,
            preroll_source=c.plan.range.preroll_source, title=c.title, offset_sec=full_start,
            pvp_score=pvp.score, pvp_signals=list(pvp.signals), clip_id=saved_ids.get(c.candidate_id),
        ))
    video = None
    if full is not None:
        video = {
            "path": FULL_VIDEO, "sizeBytes": full.size_bytes, "durationSec": full.duration_sec,
            "offsetSec": full_start, "sourceIncomplete": False, "audioStatus": "full",
        }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "gameKey": vod_game_key(source.vod_id, span.index),
        "source": "vod",
        "vodId": source.vod_id,
        "vodFile": str(source.path),
        "streamer": source.streamer,
        "vodGameIndex": span.index,
        "vodStartSec": full_start,
        "vodEndSec": full_end,
        "spanStartSec": span.start,
        "spanEndSec": span.end,
        "matchStartUtc": None,
        "matchEndUtc": None,
        "gameMode": game_mode,
        "sourceWidth": source.width,
        "sourceHeight": source.height,
        "sourceIncomplete": False,
        "matchKills": detection.k_final,
        "matchAssists": detection.a_final,
        "matchResult": match_result_dict(result, result_file),
        "portraits": portraits,
        "saveMode": save_mode,
        "fullVideo": video,
        "fullVideoError": error,
        "candidates": rows,
        "userCandidates": [],
        "markers": markers_dict(detection.markers, offset_sec=full_start),
    }


def save_game_assets(
    folder: Path, result: ResultScreen | None, portraits: PortraitCrops | None, *, game_mode: str = "battle_royale"
) -> tuple[str | None, dict[str, str | None]]:
    """결과표 이미지(`result.jpg`)와 초상화(`portrait_<칸>.jpg`)를 게임 폴더에 쓰고 파일 이름을 돌려준다. 못 쓴 것은 None.

    코발트는 선택 화면 UI 가 달라 초상화를 지원하지 않는다(detection.md §9) - 판독기가 엉뚱한 자리를 잘라 오므로 저장하지 않는다."""
    result_file = None
    if result is not None and result.image is not None:
        try:
            save_result_image(result.image, folder / "result.jpg")
            result_file = "result.jpg"
        except OSError:
            log.exception("결과 화면 이미지 저장 실패")
    names: dict[str, str | None] = {slot: None for slot in PORTRAIT_SLOTS}
    if portraits is not None and game_mode != "cobalt":
        for slot in PORTRAIT_SLOTS:
            try:
                save_portrait_image(getattr(portraits, slot), folder / f"portrait_{slot}.jpg")
                names[slot] = f"portrait_{slot}.jpg"
            except OSError:
                log.exception("초상화 이미지 저장 실패(%s)", slot)
    return result_file, names


def write_vod_game(folder: Path, data: dict) -> Path:
    return write_game_json(folder, data)


def delete_vod_games(games_dir: Path, vod_id: str, *, mode: str, only_index: int | None = None) -> list[str]:
    """이 영상의 게임 폴더(풀영상 + 게임 기록)를 지운다. 풀영상은 설정한 삭제 방식(휴지통/영구)으로, 나머지 작은 파일은 바로 지운다.

    다른 영상·스팀 게임 폴더는 건드리지 않는다. 지운 폴더 이름 목록을 돌려준다.
    """
    prefix = f"vod_{vod_id}_g"
    try:
        folders = [p for p in games_dir.iterdir() if p.is_dir() and p.name.startswith(prefix)]
    except OSError:
        return []
    removed = []
    for folder in sorted(folders):
        if only_index is not None and folder.name != vod_game_key(vod_id, only_index):
            continue
        video = folder / FULL_VIDEO
        if video.is_file():
            (permanently_delete if mode == PERMANENT else send_to_recycle_bin)([video])
        shutil.rmtree(folder, ignore_errors=True)
        removed.append(folder.name)
    return removed
