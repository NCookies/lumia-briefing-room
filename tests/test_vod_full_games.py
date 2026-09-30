import json
import subprocess
from pathlib import Path

import pytest

from lumia_briefing_room.config import Config
from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.detect.types import CombatInterval, MatchDetection
from lumia_briefing_room.pipeline import vod_full_games as vfg
from lumia_briefing_room.pipeline.clip import ClipRange
from lumia_briefing_room.pipeline.game_files import list_games, valid_key
from lumia_briefing_room.pipeline.game_store import vod_game_key
from lumia_briefing_room.pipeline.orchestrator import ClipPlan
from lumia_briefing_room.pipeline.vod_games import GameSpan

from test_vod_analyze import FFMPEG_PATH, FFPROBE_PATH, requires_ffmpeg  # noqa: F401

VOD = "3df9b3313b4e"
BASE = Path("D:/vod")


def test_vod_game_key_is_vod_id_plus_game_number_and_is_a_valid_game_key():
    key = vod_game_key(VOD, 3)
    assert key == "vod_3df9b3313b4e_g03"
    assert valid_key(key) and valid_key("20260930_002400")
    assert not valid_key("vod_xyz_g01") and not valid_key("../20260930_002400") and not valid_key("vod_3df9b3313b4e_g")


def test_keys_of_different_videos_and_games_never_collide():
    keys = {vod_game_key(v, i) for v in ("3df9b3313b4e", "eefd4a19bac1") for i in (1, 2, 10)}
    assert len(keys) == 6


def span(start=100.0, end=400.0, select_start=None):
    return GameSpan(index=2, start=start, end=end, confidence=1.0, select_start=select_start)


def test_range_starts_at_the_character_select_screen_when_it_was_found():
    start, end = vfg.vod_game_range(span(select_start=40.0), result_at=410.0, prev_end=None, next_start=None, duration=900.0)
    assert start == 40.0
    assert end == 410.0 + vfg.RESULT_DWELL_SEC


def test_range_without_a_select_screen_starts_a_bit_before_the_first_ingame_frame():
    start, _ = vfg.vod_game_range(span(), result_at=None, prev_end=None, next_start=None, duration=900.0)
    assert start == 100.0 - vfg.NO_SELECT_LEAD_SEC


def test_range_never_starts_before_the_video_or_the_previous_game_end():
    assert vfg.vod_game_range(span(start=4.0), result_at=None, prev_end=None, next_start=None, duration=900.0)[0] == 0.0
    assert vfg.vod_game_range(span(select_start=40.0), result_at=None, prev_end=60.0, next_start=None, duration=900.0)[0] == 60.0


def test_range_without_a_result_screen_ends_a_bit_after_the_last_ingame_frame():
    _, end = vfg.vod_game_range(span(), result_at=None, prev_end=None, next_start=None, duration=900.0)
    assert end == 400.0 + vfg.NO_RESULT_TAIL_SEC


def test_range_ends_before_the_next_game_starts_and_inside_the_video():
    _, end = vfg.vod_game_range(span(), result_at=405.0, prev_end=None, next_start=412.0, duration=900.0)
    assert end == 412.0
    _, end = vfg.vod_game_range(span(), result_at=405.0, prev_end=None, next_start=None, duration=410.0)
    assert end == 410.0


def test_range_never_ends_before_the_last_ingame_frame():
    _, end = vfg.vod_game_range(span(), result_at=350.0, prev_end=None, next_start=None, duration=900.0)
    assert end >= 400.0


def interval(start, end, tags):
    return CombatInterval(
        start=start, end=end, tags=frozenset(tags), k_delta=1 if "kill" in tags else 0, a_delta=0,
        died=False, day_night="day", confidence=0.9, game_day=2, region="묘지",
    )


def make_candidates():
    ivs = [interval(150.0, 170.0, {"kill"}), interval(300.0, 320.0, {"no_result"})]
    plans = [
        ClipPlan(range=ClipRange(145.0, 178.0, "combat"), intervals=[ivs[0]]),
        ClipPlan(range=ClipRange(295.0, 328.0, "combat"), intervals=[ivs[1]]),
    ]
    return vfg.name_vod_candidates(plans, VOD, 2, duration=900.0)


def test_candidate_id_is_the_clip_id_the_old_analysis_would_have_made():
    cands = make_candidates()
    assert [c.candidate_id for c in cands] == ["vod_3df9b3313b4e_g02_000145", "vod_3df9b3313b4e_g02_000295"]
    assert all(c.candidate_id == c.clip_id for c in cands)
    assert cands[0].title == "2일차 낮 묘지 교전"


def screen(t=410.0):
    return ResultScreen(
        placement=1, total=7, match_type="rank", match_label="랭크", outcome="최종 생존", nickname="스트리머",
        stats={"tk": 5, "kills": 1, "deaths": 0, "assists": 0}, image=None, t=t,
    )


def source(tmp_path):
    return vfg.VodSource(
        vod_id=VOD, path=tmp_path / "방송.mp4", streamer="하이용가리", width=1920, height=1080,
        duration_sec=900.0, size_bytes=2**30,
    )


def game_dict(tmp_path, *, full=None, error=None, saved=None, mode="auto"):
    detection = MatchDetection(
        intervals=[], k_final=3, a_final=1, gaps=[], source_incomplete=False,
        markers=[(160.0, "kill"), (310.0, "death")],
    )
    return vfg.vod_game_dict(
        source=source(tmp_path), span=span(select_start=40.0), game_mode="battle_royale", detection=detection,
        candidates=make_candidates(), saved_ids=saved or {}, full_start=40.0, full_end=425.0,
        full=full, error=error, result=screen(), result_file="result.jpg",
        portraits={"me": "portrait_me.jpg", "teammate1": None, "teammate2": None}, save_mode=mode, cfg=Config(),
    )


def test_game_json_records_where_the_game_came_from():
    data = game_dict(BASE)
    assert data["source"] == "vod" and data["vodId"] == VOD and data["gameKey"] == "vod_3df9b3313b4e_g02"
    assert data["vodGameIndex"] == 2 and data["streamer"] == "하이용가리"
    assert (data["vodStartSec"], data["vodEndSec"]) == (40.0, 425.0)
    assert (data["spanStartSec"], data["spanEndSec"]) == (100.0, 400.0)
    assert data["sourceWidth"] == 1920 and data["gameMode"] == "battle_royale"
    assert data["matchStartUtc"] is None and data["matchResult"]["placement"] == 1
    assert data["matchKills"] == 3 and data["portraits"]["me"] == "portrait_me.jpg"
    assert data["saveMode"] == "auto"


def test_game_json_times_are_relative_to_the_full_video_start():
    data = game_dict(BASE)
    first = data["candidates"][0]
    assert (first["start"], first["end"]) == (105.0, 138.0)
    assert (first["combatStart"], first["combatEnd"]) == (110.0, 130.0)
    assert first["certain"] is True and data["candidates"][1]["certain"] is False
    assert data["markers"] == [{"t": 120.0, "kind": "kill"}, {"t": 270.0, "kind": "death"}]


def test_game_json_marks_candidates_that_already_have_a_saved_clip():
    data = game_dict(BASE, saved={"vod_3df9b3313b4e_g02_000145": "vod_3df9b3313b4e_g02_000145"})
    assert data["candidates"][0]["user"] == {"savedClipId": "vod_3df9b3313b4e_g02_000145"}
    assert data["candidates"][1]["user"] == {}


def test_game_json_full_video_facts_or_the_reason_it_is_missing():
    ok = vfg.VodFullVideo(size_bytes=123, duration_sec=385.0)
    data = game_dict(BASE, full=ok)
    assert data["fullVideo"] == {
        "path": "full.mp4", "sizeBytes": 123, "durationSec": 385.0, "offsetSec": 40.0,
        "sourceIncomplete": False, "audioStatus": "full",
    }
    assert data["fullVideoError"] is None
    failed = game_dict(BASE, error="저장 공간이 부족해")
    assert failed["fullVideo"] is None and failed["fullVideoError"] == "저장 공간이 부족해"


@pytest.fixture
def vod_file(tmp_path):
    path = tmp_path / "방송.mp4"
    subprocess.run(
        [
            str(FFMPEG_PATH), "-hide_banner", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
            "-t", "60", "-c:v", "libx264", "-g", "10", "-keyint_min", "10", "-sc_threshold", "0",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )
    return path


@requires_ffmpeg
def test_cut_makes_full_mp4_of_that_range_without_reencoding(vod_file, tmp_path):
    folder = tmp_path / "games" / "vod_x_g01"
    out = vfg.cut_vod_full_video(
        vod_file, 10.0, 30.0, folder, ffmpeg_path=FFMPEG_PATH, include_audio=True, source_size=vod_file.stat().st_size,
        source_duration=60.0,
    )
    assert out.error is None and out.video is not None
    assert (folder / "full.mp4").is_file() and not (folder / "full.tmp.mp4").exists()
    assert out.video.duration_sec == pytest.approx(20.0, abs=1.5)
    assert out.video.size_bytes == (folder / "full.mp4").stat().st_size


@requires_ffmpeg
def test_cut_reports_missing_room_and_leaves_nothing(vod_file, tmp_path, monkeypatch):
    monkeypatch.setattr(vfg, "_free_bytes", lambda folder: 1024)
    folder = tmp_path / "games" / "vod_x_g01"
    out = vfg.cut_vod_full_video(
        vod_file, 10.0, 30.0, folder, ffmpeg_path=FFMPEG_PATH, include_audio=True, source_size=vod_file.stat().st_size,
        source_duration=60.0,
    )
    assert out.video is None and "저장 공간이 부족" in out.error
    assert not (folder / "full.mp4").exists()


@requires_ffmpeg
def test_cut_failure_is_reported_not_raised(tmp_path):
    out = vfg.cut_vod_full_video(
        tmp_path / "없는.mp4", 10.0, 30.0, tmp_path / "g", ffmpeg_path=FFMPEG_PATH, include_audio=True,
        source_size=10, source_duration=60.0,
    )
    assert out.video is None and out.error


def test_write_vod_game_writes_game_json_that_the_game_list_reads(tmp_path):
    games = tmp_path / "games"
    data = game_dict(tmp_path)
    vfg.write_vod_game(games / data["gameKey"], data)
    assert [g["gameKey"] for g in list_games(games)] == ["vod_3df9b3313b4e_g02"]
    assert json.loads((games / data["gameKey"] / "game.json").read_text(encoding="utf-8"))["source"] == "vod"


def test_game_assets_are_written_into_the_game_folder(tmp_path):
    import numpy as np

    from lumia_briefing_room.detect.types import PortraitCrops

    image = np.zeros((90, 160, 3), dtype=np.uint8)
    result = ResultScreen(
        placement=2, total=7, match_type="rank", match_label="랭크", outcome="x", nickname="n", stats=None, image=image
    )
    crops = PortraitCrops(me=image[:20], teammate1=image[:20], teammate2=image[:20])
    folder = tmp_path / "g"

    result_file, names = vfg.save_game_assets(folder, result, crops)

    assert result_file == "result.jpg" and (folder / "result.jpg").is_file()
    assert names == {slot: f"portrait_{slot}.jpg" for slot in ("me", "teammate1", "teammate2")}
    assert all((folder / n).is_file() for n in names.values())


def test_game_assets_are_none_without_a_result_or_portraits(tmp_path):
    result_file, names = vfg.save_game_assets(tmp_path / "g", None, None)
    assert result_file is None and names == {"me": None, "teammate1": None, "teammate2": None}


def test_cobalt_games_get_no_portraits(tmp_path):
    import numpy as np

    from lumia_briefing_room.detect.types import PortraitCrops

    image = np.zeros((20, 40, 3), dtype=np.uint8)
    crops = PortraitCrops(me=image, teammate1=image, teammate2=image)

    _, names = vfg.save_game_assets(tmp_path / "g", None, crops, game_mode="cobalt")

    assert names == {"me": None, "teammate1": None, "teammate2": None}
    assert not (tmp_path / "g" / "portrait_me.jpg").exists()
