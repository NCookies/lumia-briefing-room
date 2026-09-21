import json
import subprocess
import threading

import pytest

from lumia_briefing_room.config import Config
from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.pipeline.vod_analyze import VodCancelled, analyze_vod
from lumia_briefing_room.pipeline.vod_store import load_index, vod_id
from lumia_briefing_room.video.vod import find_ffprobe

FFMPEG_PATH = None
try:
    from lumia_briefing_room.config import discover_ffmpeg

    FFMPEG_PATH = discover_ffmpeg()
except Exception:  # pragma: no cover
    FFMPEG_PATH = None
FFPROBE_PATH = find_ffprobe(FFMPEG_PATH) if FFMPEG_PATH else None
requires_ffmpeg = pytest.mark.skipif(
    FFMPEG_PATH is None or FFPROBE_PATH is None, reason="ffmpeg/ffprobe를 찾을 수 없다"
)

DURATION = 60


@pytest.fixture
def vod_file(tmp_path):
    path = tmp_path / "방송.mp4"
    subprocess.run(
        [
            str(FFMPEG_PATH), "-hide_banner", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10",
            "-t", str(DURATION), "-c:v", "libx264", "-g", "10", "-keyint_min", "10",
            "-sc_threshold", "0", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
    )
    return path


def scripted_state(t):
    """5~55초가 한 게임. 20~28초에 교전 배지, 24초에 킬(K 0 -> 1)."""
    ingame = 5 <= t <= 55
    fighting = 20 <= t <= 28
    return FrameState(
        t=t, combat=fighting if ingame else None,
        face_value=110.0 if ingame else None, face_sat=25.0 if ingame else None,
        k=(1 if t >= 24 else 0) if ingame else None, a=0 if ingame else None,
        day_night="day" if ingame else None, spectating=False if ingame else None,
        game_day=2 if ingame else None, team_combat=False if ingame else None,
    )


def read_frame(frame, t):
    return scripted_state(round(t))


def make_cfg(base):
    cfg = Config()
    cfg.paths.vod_clips = base / "vodclips"
    cfg.vod.min_game_sec = 20.0
    cfg.clip.preroll_sec = 3
    cfg.clip.postroll_sec = 3
    cfg.filter.min_duration_sec = 2
    return cfg


def no_result(video, span, next_start):
    return None


def screen():
    return ResultScreen(
        placement=1, total=7, match_type="rank", match_label="랭크", outcome="최종 생존",
        nickname="스트리머", character="마르티나", character_raw="MARTIN",
        stats={"tk": 5, "kills": 1, "deaths": 0, "assists": 0}, image=None,
    )


def run(base, vod_file, **kw):
    cfg = kw.pop("cfg", None) or make_cfg(base)
    args = dict(ffmpeg_path=FFMPEG_PATH, read_frame=read_frame, find_result=no_result)
    args.update(kw)
    return analyze_vod(vod_file, cfg, **args), cfg


@requires_ffmpeg
def test_analyze_makes_clips_metadata_and_index(vod_file, tmp_path):
    index, cfg = run(tmp_path, vod_file, find_result=lambda v, s, n: screen())

    root = cfg.paths.vod_clips
    metas = sorted(root.glob("vod_*.json"))
    assert index["status"] == "done"
    assert len(index["games"]) == 1 and len(metas) >= 1
    meta = json.loads(metas[0].read_text(encoding="utf-8"))
    assert meta["source"] == "vod" and meta["vodId"] == vod_id(vod_file)
    assert meta["vodGameIndex"] == 1
    assert "kill" in meta["tags"] and meta["gameDay"] == 2
    assert meta["myCharacter"] == "마르티나" and meta["matchResult"]["placement"] == 1
    assert metas[0].with_suffix(".mp4").exists()
    assert (root / ".thumbs" / f"{metas[0].stem}.jpg").exists()
    assert load_index(root, vod_id(vod_file))["clips"] == [m.stem for m in metas]


@requires_ffmpeg
def test_index_records_video_facts_and_game_summary(vod_file, tmp_path):
    index, _ = run(tmp_path, vod_file, find_result=lambda v, s, n: screen())

    assert (index["width"], index["height"]) == (64, 48)
    assert index["durationSec"] == pytest.approx(DURATION, abs=0.5)
    game = index["games"][0]
    assert (game["startSec"], game["endSec"]) == (5.0, 55.0)
    assert game["result"]["placement"] == 1
    assert game["clipIds"] and game["kFinal"] == 1


@requires_ffmpeg
def test_progress_is_reported_and_reaches_the_end(vod_file, tmp_path):
    seen = []

    run(tmp_path, vod_file, on_progress=seen.append)

    assert seen and seen[-1].phase == "done" and seen[-1].fraction == 1.0
    fractions = [p.fraction for p in seen]
    assert fractions == sorted(fractions)
    assert {"decode", "games", "cut"} <= {p.phase for p in seen}


@requires_ffmpeg
def test_cancel_saves_progress_and_resume_gives_the_same_result(vod_file, tmp_path):
    cfg = make_cfg(tmp_path)
    cancel = threading.Event()
    frames_seen = []

    def cancelling(frame, t):
        frames_seen.append(t)
        if len(frames_seen) == 25:
            cancel.set()
        return scripted_state(round(t))

    with pytest.raises(VodCancelled):
        analyze_vod(vod_file, cfg, ffmpeg_path=FFMPEG_PATH, read_frame=cancelling,
                    find_result=no_result, cancel=cancel)
    partial = load_index(cfg.paths.vod_clips, vod_id(vod_file))
    assert partial["status"] == "cancelled" and not list(cfg.paths.vod_clips.glob("vod_*.json"))

    resumed_frames = []

    def counting(frame, t):
        resumed_frames.append(t)
        return scripted_state(round(t))

    index = analyze_vod(vod_file, cfg, ffmpeg_path=FFMPEG_PATH, read_frame=counting, find_result=no_result)

    assert index["status"] == "done"
    assert min(resumed_frames) >= 24
    fresh, _ = run(tmp_path / "fresh", vod_file)
    assert [g["startSec"] for g in index["games"]] == [g["startSec"] for g in fresh["games"]]
    assert len(index["clips"]) == len(fresh["clips"])


@requires_ffmpeg
def test_second_run_on_a_done_vod_does_nothing(vod_file, tmp_path):
    first, cfg = run(tmp_path, vod_file)
    calls = []

    def spy(frame, t):
        calls.append(t)
        return scripted_state(round(t))

    again = analyze_vod(vod_file, cfg, ffmpeg_path=FFMPEG_PATH, read_frame=spy, find_result=no_result)

    assert calls == [] and again["status"] == "done"
    assert again["clips"] == first["clips"]


@requires_ffmpeg
def test_rebuild_reuses_cache_and_moves_old_clips_to_trash(vod_file, tmp_path):
    first, cfg = run(tmp_path, vod_file)
    root = cfg.paths.vod_clips
    calls = []

    def spy(frame, t):
        calls.append(t)
        return scripted_state(round(t))

    cfg.clip.postroll_sec = 6
    again = analyze_vod(vod_file, cfg, ffmpeg_path=FFMPEG_PATH, read_frame=spy,
                        find_result=no_result, rebuild=True)

    assert calls == []
    assert again["status"] == "done" and again["clips"] == first["clips"]
    trashed = list((root / ".trash").rglob("vod_*.json"))
    assert trashed
    new_meta = json.loads((root / f"{again['clips'][0]}.json").read_text(encoding="utf-8"))
    old_meta = json.loads(trashed[0].read_text(encoding="utf-8"))
    assert new_meta["durationSec"] > old_meta["durationSec"]


@requires_ffmpeg
def test_force_redecodes_from_scratch(vod_file, tmp_path):
    _, cfg = run(tmp_path, vod_file)
    calls = []

    def spy(frame, t):
        calls.append(t)
        return scripted_state(round(t))

    analyze_vod(vod_file, cfg, ffmpeg_path=FFMPEG_PATH, read_frame=spy, find_result=no_result, force=True)

    assert len(calls) >= DURATION - 2 and min(calls) < 1


@requires_ffmpeg
def test_streamer_name_comes_from_config(vod_file, tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.vod.streamers = {vod_id(vod_file): "설정 이름"}

    index, _ = run(tmp_path, vod_file, cfg=cfg)
    meta = json.loads((cfg.paths.vod_clips / f"{index['clips'][0]}.json").read_text(encoding="utf-8"))

    assert index["streamer"] == "설정 이름" and meta["streamer"] == "설정 이름"


@requires_ffmpeg
def test_error_is_recorded_in_the_index_and_reraised(vod_file, tmp_path):
    cfg = make_cfg(tmp_path)

    def boom(frame, t):
        raise RuntimeError("판독 실패")

    with pytest.raises(RuntimeError):
        analyze_vod(vod_file, cfg, ffmpeg_path=FFMPEG_PATH, read_frame=boom, find_result=no_result)

    index = load_index(cfg.paths.vod_clips, vod_id(vod_file))
    assert index["status"] == "error" and "판독 실패" in index["error"]


@requires_ffmpeg
def test_result_failure_does_not_stop_clip_creation(vod_file, tmp_path):
    def broken(video, span, next_start):
        raise RuntimeError("ocr 실패")

    index, _ = run(tmp_path, vod_file, find_result=broken)

    assert index["status"] == "done" and index["clips"]
    assert index["games"][0]["result"] is None


@requires_ffmpeg
def test_index_records_the_analysis_version(vod_file, tmp_path):
    from lumia_briefing_room.pipeline.vod_analyze import ANALYSIS_VERSION

    index, _ = run(tmp_path, vod_file)

    assert index["analysisVersion"] == ANALYSIS_VERSION


@requires_ffmpeg
def test_rebuild_redecodes_when_the_cache_comes_from_an_older_reader(vod_file, tmp_path):
    first, cfg = run(tmp_path, vod_file)
    stale = load_index(cfg.paths.vod_clips, vod_id(vod_file))
    stale["analysisVersion"] = 1
    from lumia_briefing_room.pipeline.vod_store import save_index

    save_index(cfg.paths.vod_clips, stale)
    calls = []

    def spy(frame, t):
        calls.append(t)
        return scripted_state(round(t))

    analyze_vod(vod_file, cfg, ffmpeg_path=FFMPEG_PATH, read_frame=spy, find_result=no_result, rebuild=True)

    assert len(calls) >= DURATION - 2 and min(calls) < 1


@requires_ffmpeg
def test_done_vod_with_an_older_reader_is_left_alone_without_rebuild(vod_file, tmp_path):
    _, cfg = run(tmp_path, vod_file)
    stale = load_index(cfg.paths.vod_clips, vod_id(vod_file))
    stale["analysisVersion"] = 1
    from lumia_briefing_room.pipeline.vod_store import save_index

    save_index(cfg.paths.vod_clips, stale)
    calls = []

    def spy(frame, t):
        calls.append(t)
        return scripted_state(round(t))

    analyze_vod(vod_file, cfg, ffmpeg_path=FFMPEG_PATH, read_frame=spy, find_result=no_result)

    assert calls == []


@requires_ffmpeg
def test_partial_cache_from_an_older_reader_is_discarded_on_resume(vod_file, tmp_path):
    from lumia_briefing_room.pipeline.vod_store import save_index

    cfg = make_cfg(tmp_path)
    cancel = threading.Event()
    seen = []

    def cancelling(frame, t):
        seen.append(t)
        if len(seen) == 20:
            cancel.set()
        return scripted_state(round(t))

    with pytest.raises(VodCancelled):
        analyze_vod(vod_file, cfg, ffmpeg_path=FFMPEG_PATH, read_frame=cancelling,
                    find_result=no_result, cancel=cancel)
    partial = load_index(cfg.paths.vod_clips, vod_id(vod_file))
    partial["analysisVersion"] = 1
    save_index(cfg.paths.vod_clips, partial)
    resumed = []

    def counting(frame, t):
        resumed.append(t)
        return scripted_state(round(t))

    analyze_vod(vod_file, cfg, ffmpeg_path=FFMPEG_PATH, read_frame=counting, find_result=no_result)

    assert min(resumed) < 1
