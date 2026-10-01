"""게임 하나를 다시 분석한다(스팀 녹화 탭 게임 행 `⋯` → `다시 분석`). (plan-fullvideo.md §3.12)

결과 화면·초상화를 잘못 읽었거나 후보가 이상할 때 쓴다. 두 가지 방식이 있다.

- **full**: 원본 스팀 녹화가 링버퍼에 남아 있으면 풀영상·후보·마커·결과표·초상화를 전부 새로 만든다(`process_match`).
- **candidates**: 원본이 없으면(시간이 지나 지워짐) 이미 저장한 풀영상에서 후보·마커·결과표·초상화만 다시 찾는다(영상 파일 분석과 같은 판독).

새 결과는 작업 폴더에 다 만든 뒤에만 기존 것을 바꾼다 - 실패하면 기존 게임은 그대로다. 고정·보관한 클립·직접 추가한 구간·수동으로 고친 결과는
이어 붙인다(`carry_over`). 후보의 무시·이름·범위 수정은 새 후보로 바뀌므로 초기화된다.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lumia_briefing_room.config import Config
from lumia_briefing_room.detect.pvp import score_interval
from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.detect.types import FrameState, PortraitCrops
from lumia_briefing_room.pipeline.filters import apply_filter
from lumia_briefing_room.pipeline.game_candidates import MIN_LENGTH_SEC
from lumia_briefing_room.pipeline.game_edit import carry_user_fields
from lumia_briefing_room.pipeline.game_files import GameNotFound, game_dir, has_full_video, load_game, update_game
from lumia_briefing_room.pipeline.game_store import FULL_VIDEO, GAME_JSON, candidate_dict, markers_dict
from lumia_briefing_room.pipeline.legacy_games import saved_clip_ids
from lumia_briefing_room.pipeline.metadata import match_result_dict
from lumia_briefing_room.pipeline.orchestrator import _aggregate_interval, _plan_clips, default_title, next_phase_clip_index, process_match
from lumia_briefing_room.pipeline.rebuild_full_video import RebuildError, _session_and_range
from lumia_briefing_room.pipeline.vod_analyze import (
    _default_find_portraits,
    _default_find_result,
    _default_reader,
    _safe_portraits,
    _safe_result,
)
from lumia_briefing_room.pipeline.vod_detect import detect_games
from lumia_briefing_room.pipeline.vod_full_games import save_game_assets
from lumia_briefing_room.pipeline.vod_games import split_games
from lumia_briefing_room.video.session import RecordingSession
from lumia_briefing_room.video.vod import VodFileSource, find_ffprobe, probe_video

log = logging.getLogger(__name__)

REANALYZE_FULL = "full"
REANALYZE_CANDIDATES = "candidates"
_PORTRAIT_SLOTS = ("me", "teammate1", "teammate2")
_DECODE_SHARE = 0.75


class ReanalyzeError(Exception):
    """다시 분석할 수 없는 이유를 사용자에게 그대로 보여 줄 수 있는 문장으로 담는다."""


LocateSource = Callable[[dict, "Path | None", Callable[[Path], RecordingSession]], tuple]


def _default_locate(game: dict, recording_root: Path | None, load_session: Callable[[Path], RecordingSession]) -> tuple:
    return _session_and_range(game, recording_root, load_session)


def reanalyze_mode(
    game: dict, games_dir: Path, recording_root: Path | None,
    load_session: Callable[[Path], RecordingSession] = RecordingSession.load, locate_source: LocateSource | None = None,
) -> str | None:
    """원본 녹화가 남았으면 full, 없어도 풀영상이 있으면 candidates, 둘 다 없으면 None."""
    locate = locate_source or _default_locate
    try:
        locate(game, recording_root, load_session)
        return REANALYZE_FULL
    except (RebuildError, ReanalyzeError):
        pass
    return REANALYZE_CANDIDATES if has_full_video(games_dir, game.get("gameKey") or "") else None


# ---------- 이어 붙이기 ----------

def _offset(game: dict) -> float:
    return float((game.get("fullVideo") or {}).get("offsetSec") or 0.0)


def _saved_entries(old: dict) -> list[dict]:
    """옛 게임에서 클립이 있는 후보: 세션 기준 저장 범위."""
    base = _offset(old)
    entries = []
    for cand in (old.get("candidates") or []):
        user = cand.get("user") or {}
        if not user.get("savedClipId"):
            continue
        start, end = (user["savedStart"], user["savedEnd"]) if "savedStart" in user and "savedEnd" in user else (cand["start"], cand["end"])
        entries.append({"clip": user["savedClipId"], "start": start + base, "end": end + base, "title": cand.get("title") or "보관한 클립"})
    return entries


def carry_over(old: dict, new: dict) -> None:
    """옛 게임의 사용자 상태를 새 게임(`new`, 제자리에서 고친다)에 이어 붙인다."""
    old_base, new_base = _offset(old), _offset(new)
    duration = float((new.get("fullVideo") or {}).get("durationSec") or 0.0)

    carry_user_fields(old, new)
    if new.get("matchResultSource") != "manual" and old.get("matchResult") and (
        not new.get("matchResult") or (new["matchResult"].get("placement") is None and new["matchResult"].get("outcome") is None)
    ):
        new["matchResult"] = old["matchResult"]
    portraits = dict(new.get("portraits") or {})
    for slot in _PORTRAIT_SLOTS:
        if not portraits.get(slot) and (old.get("portraits") or {}).get(slot):
            portraits[slot] = old["portraits"][slot]
    new["portraits"] = portraits

    def clamp(start: float, end: float) -> tuple[float, float] | None:
        start = max(0.0, start)
        end = min(duration, end) if duration else end
        return (round(start, 3), round(end, 3)) if end - start >= MIN_LENGTH_SEC else None

    kept_users = []
    for cand in old.get("userCandidates") or []:
        user = dict(cand.get("user") or {})
        moved = clamp(cand["start"] + old_base - new_base, cand["end"] + old_base - new_base)
        if moved is None:
            continue
        if "savedStart" in user and "savedEnd" in user:
            user["savedStart"], user["savedEnd"] = round(user["savedStart"] + old_base - new_base, 3), round(user["savedEnd"] + old_base - new_base, 3)
        kept_users.append({**cand, "start": moved[0], "end": moved[1], "user": user})

    free = _saved_entries(old)
    cands = new.get("candidates") or []
    pairs = []
    for index, cand in enumerate(cands):
        lo, hi = cand["start"] + new_base, cand["end"] + new_base
        for entry in free:
            overlap = min(hi, entry["end"]) - max(lo, entry["start"])
            if overlap > 0:
                pairs.append((overlap, index, entry["clip"]))
    used_cands: set[int] = set()
    used_clips: set[str] = set()
    by_clip = {e["clip"]: e for e in free}
    for overlap, index, clip in sorted(pairs, key=lambda p: -p[0]):
        if index in used_cands or clip in used_clips:
            continue
        used_cands.add(index)
        used_clips.add(clip)
        entry = by_clip[clip]
        s, e = round(entry["start"] - new_base, 3), round(entry["end"] - new_base, 3)
        cands[index]["user"] = {"savedClipId": clip, "savedStart": s, "savedEnd": e, "start": s, "end": e}

    key = new["gameKey"]
    number = 1 + max((int(c["id"].rsplit("_u", 1)[1]) for c in kept_users if "_u" in c["id"]), default=0)
    for entry in free:
        if entry["clip"] in used_clips:
            continue
        moved = clamp(entry["start"] - new_base, entry["end"] - new_base)
        if moved is None:
            continue
        kept_users.append({
            "id": f"{key}_u{number}", "start": moved[0], "end": moved[1], "title": entry["title"], "tags": [], "certain": False,
            "user": {"savedClipId": entry["clip"], "savedStart": moved[0], "savedEnd": moved[1]},
        })
        number += 1
    new["userCandidates"] = kept_users


# ---------- 풀영상에서 후보만 다시 찾기 ----------

@dataclass
class Redetected:
    candidates: list[dict]
    markers: list[dict]
    match_kills: int | None
    match_assists: int | None
    game_mode: str
    result: ResultScreen | None
    portraits: PortraitCrops | None


def redetect_candidates(
    full_video: Path, cfg: Config, ffmpeg_path: Path, *, key: str,
    on_progress: Callable[[float], None] | None = None, cancel: threading.Event | None = None,
    read_frame=None, source_factory=None, find_result=None, find_portraits=None,
) -> Redetected:
    """저장한 풀영상(0초 = 풀영상 시작) 한 편에서 후보·마커·결과 화면·초상화를 영상 파일 분석과 같은 판독으로 다시 찾는다."""
    ffprobe = find_ffprobe(ffmpeg_path)
    info = probe_video(full_video, ffprobe_path=ffprobe)
    reader = read_frame or _default_reader(info.width, info.height)

    def factory(start: float):
        if source_factory is not None:
            return source_factory(start)
        return VodFileSource(full_video, ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe, start_sec=start, hwaccel=cfg.vod.hwaccel)

    states: list[FrameState] = []
    gen = factory(0.0).frames()
    try:
        for count, (t, frame) in enumerate(gen, start=1):
            if cancel is not None and cancel.is_set():
                raise ReanalyzeError("다시 분석을 취소했습니다")
            states.append(reader(frame, t))
            if on_progress is not None and info.duration_sec and count % 30 == 0:
                on_progress(min(1.0, t / info.duration_sec) * _DECODE_SHARE)
    finally:
        gen.close()

    spans = [s for s in split_games(states, max_gap_sec=cfg.vod.game_gap_sec, min_game_sec=cfg.vod.min_game_sec) if not s.practice]
    if not spans:
        raise ReanalyzeError("풀영상에서 게임 화면을 찾지 못했습니다. 기존 후보를 그대로 둡니다")
    span = max(spans, key=lambda s: s.end - s.start)
    (detection,) = detect_games(states, [span])
    mode = detection.detection.game_mode
    plans = _plan_clips(apply_filter(detection.detection.intervals, cfg.filter, game_mode=mode), cfg.clip, game_mode=mode)

    candidates: list[dict] = []
    phase_counts: dict[int | None, int] = {}
    for n, plan in enumerate(plans, start=1):
        aggregated = _aggregate_interval(plan.intervals)
        start, end = max(0.0, plan.range.start), min(info.duration_sec, plan.range.end)
        pvp = score_interval(aggregated, cfg.filter.pvp_weights)
        title = default_title(
            aggregated.day_night, aggregated.region, aggregated.game_day,
            cobalt_phase=aggregated.cobalt_phase, clip_index=next_phase_clip_index(phase_counts, aggregated.cobalt_phase),
        )
        candidates.append(candidate_dict(
            f"{key}_{n:02d}", interval=aggregated, start=start, end=end, preroll_source=plan.range.preroll_source, title=title,
            offset_sec=0.0, pvp_score=pvp.score, pvp_signals=list(pvp.signals), clip_id=None,
        ))

    if on_progress is not None:
        on_progress(_DECODE_SHARE)
    find_res = find_result or _default_find_result(ffmpeg_path, info.width, info.height, cfg.vod.hwaccel)
    find_por = find_portraits or _default_find_portraits(ffmpeg_path, info.width, info.height, cfg.vod.hwaccel)
    result = _safe_result(find_res, full_video, span, None)
    portraits = _safe_portraits(find_por, full_video, span)
    return Redetected(
        candidates=candidates, markers=markers_dict(detection.detection.markers, offset_sec=0.0),
        match_kills=detection.detection.k_final, match_assists=detection.detection.a_final, game_mode=mode, result=result,
        portraits=portraits,
    )


# ---------- 바꿔치기 ----------

def _replace_with_retry(src: Path, dst: Path, *, attempts: int = 20) -> None:
    """Windows 는 브라우저가 풀영상을 읽는 중이면 바꿔치기가 PermissionError 로 실패한다 - 잠깐 기다려 다시 시도한다."""
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.25)


def _install(staged: Path, dest: Path) -> None:
    """작업 폴더의 파일을 게임 폴더로 옮긴다. 영상 → 이미지 → game.json 순서라 game.json 이 바뀔 때는 나머지가 다 있다."""
    dest.mkdir(parents=True, exist_ok=True)
    files = sorted((p for p in staged.iterdir() if p.is_file() and not p.name.endswith(".tmp")), key=lambda p: (p.name == GAME_JSON, p.name != FULL_VIDEO, p.name))
    for path in files:
        _replace_with_retry(path, dest / path.name)


def reanalyze_game(
    *,
    games_dir: Path,
    clips_dir: Path,
    key: str,
    recording_root: Path | None,
    cfg: Config,
    ffmpeg_path: Path,
    staging_dir: Path,
    process: Callable = process_match,
    load_session: Callable[[Path], RecordingSession] = RecordingSession.load,
    locate_source: LocateSource | None = None,
    on_progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
    read_frame=None,
    source_factory=None,
    find_result=None,
    find_portraits=None,
) -> str:
    """방식(`full`/`candidates`)을 돌려준다. `clips_dir` 는 클립 정보(library) 폴더, `staging_dir` 는 게임 폴더와 같은 드라이브의 작업 폴더다."""
    try:
        old = load_game(games_dir, key)
    except GameNotFound as exc:
        raise ReanalyzeError("게임을 찾을 수 없습니다") from exc
    if old.get("source") == "vod":
        raise ReanalyzeError("영상 파일 게임은 영상 묶음에서 다시 분석합니다")
    locate = locate_source or _default_locate
    mode = reanalyze_mode(old, games_dir, recording_root, load_session, locate)
    if mode is None:
        raise ReanalyzeError("원본 녹화도 풀영상도 남아 있지 않아 다시 분석할 수 없습니다")

    work = staging_dir / uuid.uuid4().hex
    work_games, work_clips = work / "games", work / "clips"
    work_games.mkdir(parents=True)
    work_clips.mkdir(parents=True)
    folder = game_dir(games_dir, key)
    try:
        if mode == REANALYZE_FULL:
            session, start, end = locate(old, recording_root, load_session)
            process(
                session, start, end, cfg, ffmpeg_path=ffmpeg_path, clips_dir=work_clips, games_dir=work_games,
                existing_clip_ids=saved_clip_ids(old, clips_dir), on_progress=(lambda f: on_progress(f * 0.95)) if on_progress else None,
                cancel=cancel,
            )
            staged_folder = game_dir(work_games, key)
            if not has_full_video(work_games, key):
                try:
                    reason = load_game(work_games, key).get("fullVideoError")
                except GameNotFound:
                    reason = None
                raise ReanalyzeError(reason or "풀영상을 만들지 못했습니다. 기존 게임을 그대로 둡니다")
            update_game(work_games, key, lambda data: carry_over(old, data))
            _install(staged_folder, folder)
        else:
            redetected = redetect_candidates(
                folder / FULL_VIDEO, cfg, ffmpeg_path, key=key, on_progress=on_progress, cancel=cancel, read_frame=read_frame,
                source_factory=source_factory, find_result=find_result, find_portraits=find_portraits,
            )
            assets = work / "assets"
            assets.mkdir()
            result_file, portrait_names = save_game_assets(assets, redetected.result, redetected.portraits, game_mode=redetected.game_mode)

            for path in assets.iterdir():
                _replace_with_retry(path, folder / path.name)
            update_game(games_dir, key, lambda data: _apply_candidates(data, old, redetected, result_file, portrait_names))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if on_progress is not None:
        on_progress(1.0)
    return mode


def _apply_candidates(data: dict, old: dict, found: Redetected, result_file: str | None, portraits: dict) -> None:
    data.update(
        candidates=found.candidates, markers=found.markers, matchKills=found.match_kills, matchAssists=found.match_assists,
        gameMode=found.game_mode,
        matchResult=match_result_dict(found.result, result_file) if found.result is not None else None, portraits=portraits,
    )
    carry_over(old, data)
