import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api import game_routes
from lumia_briefing_room.api import vods as vods_module
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig, resolve_paths, save_config
from lumia_briefing_room.pipeline import clip_from_full as cff
from lumia_briefing_room.pipeline.vod_store import cache_path, save_index, vod_id

STEAM_KEY = "20260930_002400"


def write_video(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def cand(cid, start, end, certain=False, user=None):
    return {"id": cid, "start": start, "end": end, "combatStart": start + 5, "combatEnd": end - 5, "title": cid,
            "tags": ["kill"] if certain else ["no_result"], "certain": certain, "user": user or {},
            "killDelta": 1 if certain else 0, "assistDelta": 0, "died": False, "pvpScore": 0.8, "pvpSignals": [],
            "gameDay": 2, "dayNight": "day", "region": "묘지", "detectorConfidence": 0.9}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(vods_module, "discover_ffmpeg", lambda: tmp_path / "ffmpeg.exe")
    monkeypatch.setattr(vods_module, "_probe_info", lambda path, ffmpeg: None)
    monkeypatch.setattr(game_routes, "discover_ffmpeg", lambda: Path("ffmpeg"))
    videos = tmp_path / "videos"
    a = write_video(videos / "a.mp4", b"A" * 3000)
    vod_dir, games = tmp_path / "vod", tmp_path / "games"
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", vod_clips=vod_dir, temp=tmp_path / "tmp", games=games))
    cfg.vod.sources = [str(videos)]
    config_path = tmp_path / "config.json"
    save_config(cfg, config_path)
    client = TestClient(create_app(cfg, config_path=config_path))
    vid = vod_id(a)
    key = f"vod_{vid}_g01"

    folder = games / key
    folder.mkdir(parents=True)
    (folder / "full.mp4").write_bytes(b"0123456789" * 100)
    game = {
        "gameKey": key, "source": "vod", "vodId": vid, "vodFile": str(a), "streamer": "하이용가리", "vodGameIndex": 1,
        "vodStartSec": 1000.0, "vodEndSec": 1600.0, "spanStartSec": 1060.0, "spanEndSec": 1580.0,
        "matchStartUtc": None, "matchEndUtc": None, "gameMode": "battle_royale", "sourceWidth": 1920,
        "sourceHeight": 1080, "matchKills": 2, "matchAssists": 1, "matchResult": None, "portraits": {}, "pinned": False,
        "fullVideo": {"path": "full.mp4", "sizeBytes": 1000, "durationSec": 600.0, "offsetSec": 1000.0,
                      "sourceIncomplete": False, "audioStatus": "full"},
        "candidates": [cand(f"vod_{vid}_g01_001100", 100, 140, certain=True), cand(f"vod_{vid}_g01_001300", 300, 330)],
        "userCandidates": [], "markers": [],
    }
    (folder / "game.json").write_text(json.dumps(game), encoding="utf-8")
    steam = games / STEAM_KEY
    steam.mkdir()
    (steam / "game.json").write_text(json.dumps({
        "gameKey": STEAM_KEY, "matchStartUtc": "2026-09-30T00:24:00Z", "fullVideo": None, "candidates": [],
        "userCandidates": [], "markers": [],
    }), encoding="utf-8")

    cuts = []
    monkeypatch.setattr(cff, "_run_ffmpeg", lambda cmd: (cuts.append(cmd), Path(cmd[-1]).write_bytes(b"clip")))
    monkeypatch.setattr(
        cff, "make_thumbnail", lambda clip, out, **kw: out.parent.mkdir(parents=True, exist_ok=True) or out.write_bytes(b"t")
    )
    client.cuts, client.vid, client.key, client.a, client.tmp = cuts, vid, key, a, tmp_path
    client.vod_dir, client.games = resolve_paths(cfg.paths).library_vod, games
    client.vod_videos = vod_dir
    return client


def test_steam_list_is_the_default_and_never_shows_vod_games(env):
    keys = [g["key"] for g in env.get("/api/games").json()["games"]]
    assert keys == [STEAM_KEY]


def test_vod_list_has_only_vod_games_with_where_they_came_from(env):
    (game,) = env.get("/api/games", params={"source": "vod"}).json()["games"]
    assert game["key"] == env.key and game["source"] == "vod" and game["vodId"] == env.vid
    assert game["gameIndex"] == 1 and game["hasFullVideo"] is True and game["candidateCount"] == 2
    assert game["streamer"] == "하이용가리" and (game["vodStartSec"], game["vodEndSec"]) == (1000.0, 1600.0)
    both = env.get("/api/games", params={"source": "all"}).json()["games"]
    assert {g["key"] for g in both} == {STEAM_KEY, env.key}


def test_listing_vod_games_moves_the_old_analysis_into_legacy_games_once(env):
    vid2 = "aaaaaaaaaaaa"
    save_index(env.vod_dir, {
        "id": vid2, "path": str(env.tmp / "gone.mp4"), "status": "done", "width": 1920, "height": 1080,
        "games": [{"index": 1, "startSec": 90.0, "endSec": 600.0, "kFinal": 3, "aFinal": 1, "gameMode": "battle_royale",
                   "result": None, "clipIds": []}],
        "clips": [],
    })

    games = {g["key"]: g for g in env.get("/api/games", params={"source": "vod"}).json()["games"]}
    again = {g["key"] for g in env.get("/api/games", params={"source": "vod"}).json()["games"]}

    legacy = games[f"vod_{vid2}_g01"]
    assert legacy["legacy"] is True and legacy["hasFullVideo"] is False and set(games) == again


def test_vod_game_detail_streams_the_full_video(env):
    detail = env.get(f"/api/games/{env.key}").json()
    assert detail["source"] == "vod" and detail["hasFullVideo"] is True
    assert env.get(f"/api/games/{env.key}/video", headers={"Range": "bytes=0-9"}).status_code == 206


def test_saving_a_candidate_of_a_vod_game_makes_a_vod_clip_in_the_vod_clip_folder(env):
    cid = f"vod_{env.vid}_g01_001100"

    clip_id = env.post(f"/api/games/{env.key}/candidates/{cid}/save").json()["clipId"]

    assert clip_id == cid
    assert (env.vod_videos / f"{cid}.mp4").is_file(), "영상은 영상 파일 클립 자리에 놓인다"
    assert not (env.tmp / "clips" / f"{cid}.mp4").exists() and not (env.vod_dir / f"{cid}.mp4").exists()
    meta = json.loads((env.vod_dir / f"{cid}.json").read_text(encoding="utf-8"))
    assert meta["source"] == "vod" and meta["vodId"] == env.vid and meta["vodFile"] == str(env.a)
    assert meta["vodGameIndex"] == 1 and meta["streamer"] == "하이용가리"
    assert meta["videoOffsetSec"] == 1100.0
    assert meta["combatStartOffsetSec"] == 1105.0 and meta["combatEndOffsetSec"] == 1135.0
    assert (meta["gameStartOffsetSec"], meta["gameEndOffsetSec"]) == (1060.0, 1580.0)
    assert meta["tags"] == ["kill"] and meta["gameDay"] == 2 and meta["clipUid"]
    listed = env.get("/api/clips", params={"source": "vod"}).json()
    assert cid in [c["id"] for c in listed]
    game = env.get(f"/api/games/{env.key}").json()
    assert game["candidates"][0]["user"]["savedClipId"] == cid


def test_renaming_a_saved_vod_candidate_renames_the_clip_in_the_vod_folder(env):
    cid = f"vod_{env.vid}_g01_001100"
    env.post(f"/api/games/{env.key}/candidates/{cid}/save")

    env.patch(f"/api/games/{env.key}/candidates/{cid}", json={"title": "내 이름"})

    assert json.loads((env.vod_dir / f"{cid}.json").read_text(encoding="utf-8"))["title"] == "내 이름"


class FakeUpgrade:
    def __init__(self):
        self.calls, self.started, self.release = [], threading.Event(), threading.Event()

    def __call__(self, video, cfg, *, index, only=None, on_progress=None, cancel=None, **kw):
        self.calls.append((Path(video).name, sorted(only) if only else None))
        self.started.set()
        on_progress(0.5, "게임 1 풀영상")
        assert self.release.wait(5)
        return [f"vod_{index['id']}_g01"]


def wait_state(client, vid, state, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/vods/{vid}/analyze").json()
        if job["state"] == state:
            return job
        time.sleep(0.02)
    raise AssertionError(f"{state} 가 되지 않았다: {job}")


def make_upgradable(env):
    save_index(env.vod_dir, {
        "id": env.vid, "path": str(env.a), "status": "done", "decodeDone": True, "width": 1920, "height": 1080,
        "durationSec": 1800.0, "games": [{"index": 1, "startSec": 1060.0, "endSec": 1580.0, "clipIds": []}], "clips": [],
    })
    cache = cache_path(env.vod_dir, env.vid)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"x")


def test_vod_entry_says_whether_full_videos_can_be_built_for_old_games(env):
    entry = {v["id"]: v for v in env.get("/api/vods").json()}[env.vid]
    assert entry["canBuildFullVideos"] is False
    make_upgradable(env)
    entry = {v["id"]: v for v in env.get("/api/vods").json()}[env.vid]
    assert entry["canBuildFullVideos"] is True


def test_full_videos_of_a_vod_are_built_in_the_background_with_the_analysis_job(env, monkeypatch):
    make_upgradable(env)
    fake = FakeUpgrade()
    monkeypatch.setattr(vods_module, "upgrade_vod_games", fake)

    assert env.post(f"/api/vods/{env.vid}/full-videos").status_code == 202
    assert fake.started.wait(2)
    job = wait_state(env, env.vid, "running")
    assert job["kind"] == "fullVideos" and job["fraction"] == 0.5 and job["message"] == "게임 1 풀영상"
    assert env.post(f"/api/vods/{env.vid}/full-videos").status_code == 202, "실행 중인 같은 작업을 또 눌러도 거부하지 않는다"

    fake.release.set()
    wait_state(env, env.vid, "done")
    assert fake.calls == [("a.mp4", None)], "같은 요청이라 한 번만 돈다"


def test_full_videos_cannot_be_built_without_source_or_read_cache(env):
    assert env.post(f"/api/vods/{env.vid}/full-videos").status_code == 409
    assert env.post("/api/vods/nope/full-videos").status_code == 404


def test_one_legacy_vod_game_can_be_built_from_the_game_screen_button(env, monkeypatch):
    make_upgradable(env)
    fake = FakeUpgrade()
    fake.release.set()
    monkeypatch.setattr(vods_module, "upgrade_vod_games", fake)
    (env.games / env.key / "full.mp4").unlink()
    data = json.loads((env.games / env.key / "game.json").read_text(encoding="utf-8"))
    data.update(legacy=True, fullVideo=None)
    (env.games / env.key / "game.json").write_text(json.dumps(data), encoding="utf-8")

    assert env.get(f"/api/games/{env.key}").json()["canRebuildFullVideo"] is True
    assert env.post(f"/api/games/{env.key}/full-video").status_code == 202
    for _ in range(100):
        state = env.get(f"/api/games/{env.key}/full-video/status").json()["state"]
        if state != "running":
            break
        time.sleep(0.02)

    assert state == "done" and fake.calls == [("a.mp4", [1])]


def test_deleting_all_clips_of_a_vod_also_removes_its_game_folders_but_not_other_games(env):
    env.delete(f"/api/vods/{env.vid}/clips")

    assert not (env.games / env.key).exists() and (env.games / STEAM_KEY).exists()


def test_deleting_one_vod_game_removes_only_that_game_folder(env):
    other = env.games / f"vod_{env.vid}_g02"
    other.mkdir()
    (other / "game.json").write_text("{}", encoding="utf-8")
    save_index(env.vod_dir, {
        "id": env.vid, "path": str(env.a), "status": "done",
        "games": [{"index": 1, "startSec": 0.0, "endSec": 10.0, "clipIds": []},
                  {"index": 2, "startSec": 20.0, "endSec": 30.0, "clipIds": []}], "clips": [],
    })

    assert env.delete(f"/api/vods/{env.vid}/games/1").status_code == 200

    assert not (env.games / env.key).exists() and other.exists()


def test_deleting_a_vod_removes_its_game_folders(env):
    save_index(env.vod_dir, {"id": env.vid, "path": str(env.a), "status": "done", "games": [], "clips": []})

    assert env.delete(f"/api/vods/{env.vid}").status_code == 200

    assert not (env.games / env.key).exists() and (env.games / STEAM_KEY).exists()
