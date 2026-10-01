import json
import subprocess
from dataclasses import replace

import pytest

from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.pipeline import vod_analyze
from lumia_briefing_room.pipeline import vod_full_games as vfg
from lumia_briefing_room.pipeline.vod_analyze import analyze_vod, should_delete_source
from lumia_briefing_room.pipeline.vod_store import vod_id

from test_vod_analyze import (  # noqa: F401
    DURATION,
    FFMPEG_PATH,
    make_cfg,
    no_result,
    read_frame,
    requires_ffmpeg,
    run,
    scripted_state,
    screen,
    vod_file,
)


def games_of(cfg):
    return sorted(p for p in cfg.paths.games.iterdir() if p.is_dir())


def read_game(folder):
    return json.loads((folder / "game.json").read_text(encoding="utf-8"))


@requires_ffmpeg
def test_each_game_gets_a_full_video_and_a_game_json_in_the_shared_games_folder(vod_file, tmp_path):
    index, cfg = run(tmp_path, vod_file, find_result=lambda v, s, n: screen())

    (folder,) = games_of(cfg)
    key = f"vod_{vod_id(vod_file)}_g01"
    assert folder.name == key and index["games"][0]["gameKey"] == key
    data = read_game(folder)
    assert data["source"] == "vod" and data["vodId"] == vod_id(vod_file)
    assert data["fullVideo"]["durationSec"] > 40 and (folder / "full.mp4").is_file()
    assert data["matchResult"]["placement"] == 1 and data["gameMode"] == "battle_royale"
    assert index["games"][0]["fullVideo"] is True


@requires_ffmpeg
def test_auto_save_mode_also_saves_every_candidate_as_a_clip_linked_to_the_game(vod_file, tmp_path):
    index, cfg = run(tmp_path, vod_file)

    data = read_game(games_of(cfg)[0])
    clip_ids = index["games"][0]["clipIds"]
    assert clip_ids and [c["id"] for c in data["candidates"]] == clip_ids
    assert [c["user"]["savedClipId"] for c in data["candidates"]] == clip_ids
    assert all((cfg.paths.vod_clips / f"{cid}.mp4").is_file() for cid in clip_ids)


@requires_ffmpeg
def test_manual_save_mode_makes_the_full_video_and_candidates_but_no_clips(vod_file, tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.clip.save_mode = "manual"

    index, _ = run(tmp_path, vod_file, cfg=cfg)

    data = read_game(games_of(cfg)[0])
    assert data["saveMode"] == "manual" and (games_of(cfg)[0] / "full.mp4").is_file()
    assert len(data["candidates"]) >= 1 and all(c["user"] == {} for c in data["candidates"])
    assert not list(cfg.paths.vod_clips.glob("vod_*.json")) and index["clips"] == []


def with_select_screen(t):
    state = scripted_state(t)
    if 1 <= t <= 4:
        return replace(state, select_screen=True, select_practice=False)
    return state


@requires_ffmpeg
def test_full_video_starts_at_the_character_select_screen_and_ends_after_the_result_screen(vod_file, tmp_path):
    index, cfg = run(
        tmp_path, vod_file, read_frame=lambda f, t: with_select_screen(round(t)),
        find_result=lambda v, s, n: replace(screen(), t=57.0),
    )

    data = read_game(games_of(cfg)[0])
    assert data["vodStartSec"] == 1.0
    assert data["vodEndSec"] == pytest.approx(min(57.0 + vfg.RESULT_DWELL_SEC, DURATION), abs=0.01)
    assert (data["spanStartSec"], data["spanEndSec"]) == (5.0, 55.0)


@requires_ffmpeg
def test_practice_mode_game_is_not_a_game(vod_file, tmp_path):
    def practice(frame, t):
        state = scripted_state(round(t))
        return replace(state, select_screen=True, select_practice=True) if 1 <= round(t) <= 4 else state

    index, cfg = run(tmp_path, vod_file, read_frame=practice)

    assert index["games"] == []
    assert not cfg.paths.games.exists() or not games_of(cfg)


def test_source_is_deleted_only_when_at_least_one_game_full_video_was_saved():
    base = {"deleteSourceOnSuccess": True}
    assert should_delete_source({**base, "games": [{"fullVideo": True}, {"fullVideo": False}], "clips": []})
    assert not should_delete_source({**base, "games": [{"fullVideo": False}], "clips": ["vod_x_g01_000001"]})
    assert not should_delete_source({**base, "games": [], "clips": []})
    assert not should_delete_source({"games": [{"fullVideo": True}]})


@requires_ffmpeg
def test_source_is_deleted_in_manual_mode_because_full_videos_exist_even_with_no_clips(vod_file, tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.clip.save_mode = "manual"

    index, _ = run(tmp_path, vod_file, cfg=cfg, delete_source=True)

    assert index["clips"] == [] and not vod_file.exists() and index["sourceDeleted"] is True


@requires_ffmpeg
def test_source_is_kept_when_no_full_video_could_be_saved_even_if_clips_were_made(vod_file, tmp_path, monkeypatch):
    monkeypatch.setattr(
        vod_analyze, "cut_vod_full_video", lambda *a, **k: vfg.VodFullOutcome(None, "저장 공간이 부족해 풀영상을 만들지 못했습니다")
    )

    index, cfg = run(tmp_path, vod_file, delete_source=True)

    assert index["clips"] and vod_file.exists() and not index.get("sourceDeleted")
    data = read_game(games_dir_first(cfg))
    assert data["fullVideo"] is None and "저장 공간" in data["fullVideoError"]


def games_dir_first(cfg):
    return games_of(cfg)[0]


@requires_ffmpeg
def test_rebuild_replaces_the_game_but_keeps_pinned_and_drops_stale_games(vod_file, tmp_path):
    first, cfg = run(tmp_path, vod_file)
    folder = games_of(cfg)[0]
    data = read_game(folder)
    data["pinned"] = True
    data["title"] = "내 제목"
    data["matchResult"], data["matchResultSource"] = {"placement": 1}, "manual"
    (folder / "game.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    stale = cfg.paths.games / f"vod_{vod_id(vod_file)}_g09"
    stale.mkdir()
    (stale / "game.json").write_text("{}", encoding="utf-8")
    other = cfg.paths.games / "vod_aaaaaaaaaaaa_g01"
    other.mkdir()

    analyze_vod(vod_file, cfg, ffmpeg_path=FFMPEG_PATH, read_frame=read_frame, find_result=no_result, rebuild=True)

    kept = read_game(folder)
    assert kept["pinned"] is True and kept["title"] == "내 제목"
    assert kept["matchResult"] == {"placement": 1} and kept["matchResultSource"] == "manual"
    assert not stale.exists() and other.exists()


@requires_ffmpeg
def test_manual_mode_rebuild_keeps_clips_the_user_already_saved_and_marks_them_saved(vod_file, tmp_path):
    first, cfg = run(tmp_path, vod_file)
    cfg.clip.save_mode = "manual"

    again = analyze_vod(vod_file, cfg, ffmpeg_path=FFMPEG_PATH, read_frame=read_frame, find_result=no_result, rebuild=True)

    assert all((cfg.paths.vod_clips / f"{cid}.mp4").is_file() for cid in first["clips"])
    data = read_game(games_of(cfg)[0])
    assert [c["user"].get("savedClipId") for c in data["candidates"]] == first["games"][0]["clipIds"]
    assert again["games"][0]["clipIds"] == first["games"][0]["clipIds"]


@requires_ffmpeg
def test_cancelled_analysis_leaves_no_half_made_game_folder(vod_file, tmp_path):
    import threading

    from lumia_briefing_room.pipeline.vod_analyze import VodCancelled

    cfg = make_cfg(tmp_path)
    cancel = threading.Event()

    def cancel_on_result(video, span, next_start):
        cancel.set()
        return None

    with pytest.raises(VodCancelled):
        analyze_vod(
            vod_file, cfg, ffmpeg_path=FFMPEG_PATH, read_frame=read_frame, find_result=cancel_on_result, cancel=cancel
        )

    assert not cfg.paths.games.exists() or not any(cfg.paths.games.iterdir())
