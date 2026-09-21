import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api import vods as vods_module
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig, load_config
from lumia_briefing_room.pipeline.vod_analyze import VodCancelled, VodProgress
from lumia_briefing_room.pipeline.vod_store import save_index, vod_id


def write_video(path: Path, content: bytes = b"video-bytes" * 100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def write_vod_clip(root: Path, vid: str, game: int, start: int, **meta):
    root.mkdir(parents=True, exist_ok=True)
    cid = f"vod_{vid}_g{game:02d}_{start:06d}"
    (root / f"{cid}.mp4").write_bytes(b"x" * 100)
    data = {"title": cid, "source": "vod", "vodId": vid, "vodGameIndex": game, "tags": ["kill"],
            "pinned": False, "deletedAt": None, "thumbnailPath": None, **meta}
    (root / f"{cid}.json").write_text(json.dumps(data), encoding="utf-8")
    return cid


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(vods_module, "discover_ffmpeg", lambda: tmp_path / "ffmpeg.exe")
    monkeypatch.setattr(vods_module, "_probe_duration", lambda path, ffmpeg: None)
    videos = tmp_path / "videos"
    a = write_video(videos / "a.mp4", b"A" * 3000)
    b = write_video(videos / "sub" / "b.mkv", b"B" * 4000)
    write_video(videos / "notes.txt", b"not a video")
    vod_dir = tmp_path / "vod"
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", vod_clips=vod_dir, temp=tmp_path / "tmp"))
    cfg.vod.sources = [str(videos)]
    config_path = tmp_path / "config.json"
    from lumia_briefing_room.config import save_config
    save_config(cfg, config_path)
    app = create_app(cfg, config_path=config_path)
    return TestClient(app), a, b, vod_dir, config_path, videos


def by_id(resp):
    return {v["id"]: v for v in resp.json()}


def test_empty_when_no_sources(tmp_path):
    cfg = Config(paths=PathsConfig(vod_clips=tmp_path / "vod"))
    client = TestClient(create_app(cfg, config_path=tmp_path / "c.json"))

    assert client.get("/api/vods").json() == []


def test_lists_video_files_from_a_folder_source_ignoring_other_files(env):
    client, a, b, *_ = env

    listed = by_id(client.get("/api/vods"))

    assert set(listed) == {vod_id(a)}
    entry = listed[vod_id(a)]
    assert entry["name"] == "a.mp4" and entry["exists"] is True
    assert entry["status"] == "new" and entry["sizeBytes"] == 3000
    assert entry["games"] == [] and entry["clipCount"] == 0


def test_recursive_flag_includes_subfolders_and_files_can_be_sources(env):
    client, a, b, vod_dir, config_path, videos = env
    client.put("/api/config", json={"vod": {"recursive": True}})

    assert set(by_id(client.get("/api/vods"))) == {vod_id(a), vod_id(b)}

    client.put("/api/config", json={"vod": {"recursive": False, "sources": [str(b)]}})
    assert set(by_id(client.get("/api/vods"))) == {vod_id(b)}


def test_analyzed_vod_reports_status_games_and_live_clip_counts(env):
    client, a, b, vod_dir, *_ = env
    vid = vod_id(a)
    c1 = write_vod_clip(vod_dir, vid, 1, 10)
    write_vod_clip(vod_dir, vid, 1, 90)
    write_vod_clip(vod_dir, vid, 2, 10)
    client.post(f"/api/clips/{c1}/trash")
    save_index(vod_dir, {
        "id": vid, "path": str(a), "status": "done", "durationSec": 1234.0, "width": 1920, "height": 1080,
        "streamer": "인덱스 이름", "analyzedSec": 1234.0,
        "games": [{"index": 1, "startSec": 5.0, "endSec": 600.0, "result": {"placement": 2}, "clipIds": []},
                  {"index": 2, "startSec": 700.0, "endSec": 900.0, "result": None, "clipIds": []}],
        "clips": [],
    })

    entry = by_id(client.get("/api/vods"))[vid]

    assert entry["status"] == "done" and entry["durationSec"] == 1234.0
    assert (entry["width"], entry["height"]) == (1920, 1080)
    assert len(entry["games"]) == 2 and entry["games"][0]["result"]["placement"] == 2
    assert entry["clipCount"] == 2 and entry["trashedCount"] == 1 and entry["clipBytes"] == 200
    assert entry["streamer"] == "인덱스 이름"


def test_interrupted_analysis_is_reported_when_no_job_is_running(env):
    client, a, _, vod_dir, *_ = env
    save_index(vod_dir, {"id": vod_id(a), "path": str(a), "status": "analyzing", "analyzedSec": 300.0,
                         "durationSec": 1000.0, "games": [], "clips": []})

    assert by_id(client.get("/api/vods"))[vod_id(a)]["status"] == "interrupted"


def test_known_vod_whose_file_disappeared_is_still_listed(env):
    client, a, _, vod_dir, *_ = env
    gone = tmp = vod_dir.parent / "elsewhere.mp4"
    save_index(vod_dir, {"id": "deadbeef0001", "path": str(gone), "status": "done", "games": [], "clips": []})

    entry = by_id(client.get("/api/vods"))["deadbeef0001"]

    assert entry["exists"] is False and entry["name"] == "elsewhere.mp4" and entry["status"] == "done"


def test_streamer_name_is_saved_in_the_config_and_shown(env):
    client, a, _, _, config_path, _ = env
    vid = vod_id(a)

    resp = client.patch(f"/api/vods/{vid}", json={"streamer": "○○○"})

    assert resp.status_code == 200
    assert load_config(config_path).vod.streamers[vid] == "○○○"
    assert by_id(client.get("/api/vods"))[vid]["streamer"] == "○○○"
    assert client.patch("/api/vods/nope", json={"streamer": "x"}).status_code == 404


def test_clearing_the_streamer_name_removes_it(env):
    client, a, *_ = env
    vid = vod_id(a)
    client.patch(f"/api/vods/{vid}", json={"streamer": "이름"})

    resp = client.patch(f"/api/vods/{vid}", json={"streamer": "  "})

    assert resp.json()["streamer"] is None
    assert by_id(client.get("/api/vods"))[vid]["streamer"] is None


class FakeAnalyze:
    def __init__(self, *, fail: Exception | None = None):
        self.release = threading.Event()
        self.started = threading.Event()
        self.calls = []
        self.fail = fail

    def __call__(self, path, cfg, **kw):
        self.calls.append((Path(path).name, kw.get("force"), kw.get("rebuild")))
        self.started.set()
        kw["on_progress"](VodProgress("decode", 0.4, 1, 2, "절반 가까이"))
        while not self.release.is_set():
            if kw["cancel"].is_set():
                raise VodCancelled()
            time.sleep(0.01)
        if self.fail:
            raise self.fail
        return {"status": "done", "games": [], "clips": []}


def wait_for(client, vid, state, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/vods/{vid}/analyze").json()
        if job["state"] == state:
            return job
        time.sleep(0.02)
    raise AssertionError(f"{state} 가 되지 않았다: {job}")


def test_analyze_runs_in_the_background_and_reports_progress(env, monkeypatch):
    client, a, *_ = env
    fake = FakeAnalyze()
    monkeypatch.setattr(vods_module, "analyze_vod", fake)
    vid = vod_id(a)

    assert client.post(f"/api/vods/{vid}/analyze", json={}).status_code == 202
    assert fake.started.wait(2)
    job = wait_for(client, vid, "running")

    assert job["phase"] == "decode" and job["fraction"] == 0.4
    assert job["games"] == 1 and job["clips"] == 2 and job["message"] == "절반 가까이"
    assert by_id(client.get("/api/vods"))[vid]["status"] == "analyzing"

    fake.release.set()
    wait_for(client, vid, "done")
    assert fake.calls == [("a.mp4", False, False)]


def test_only_one_analysis_runs_at_a_time_and_unknown_vod_is_404(env, monkeypatch):
    client, a, *_ = env
    fake = FakeAnalyze()
    monkeypatch.setattr(vods_module, "analyze_vod", fake)
    vid = vod_id(a)
    client.post(f"/api/vods/{vid}/analyze", json={})
    assert fake.started.wait(2)

    assert client.post(f"/api/vods/{vid}/analyze", json={}).status_code == 409
    assert client.post("/api/vods/nope/analyze", json={}).status_code == 404
    fake.release.set()
    wait_for(client, vid, "done")


def test_force_and_rebuild_flags_are_passed_through(env, monkeypatch):
    client, a, *_ = env
    fake = FakeAnalyze()
    fake.release.set()
    monkeypatch.setattr(vods_module, "analyze_vod", fake)
    vid = vod_id(a)

    client.post(f"/api/vods/{vid}/analyze", json={"force": True})
    wait_for(client, vid, "done")
    client.post(f"/api/vods/{vid}/analyze", json={"rebuild": True})
    time.sleep(0.2)

    assert fake.calls[0] == ("a.mp4", True, False) and fake.calls[1] == ("a.mp4", False, True)


def test_cancel_stops_the_running_analysis(env, monkeypatch):
    client, a, *_ = env
    fake = FakeAnalyze()
    monkeypatch.setattr(vods_module, "analyze_vod", fake)
    vid = vod_id(a)
    client.post(f"/api/vods/{vid}/analyze", json={})
    assert fake.started.wait(2)

    assert client.post(f"/api/vods/{vid}/analyze/cancel").status_code == 200
    wait_for(client, vid, "cancelled")

    assert client.post(f"/api/vods/{vid}/analyze/cancel").status_code == 409


def test_analysis_errors_are_reported(env, monkeypatch):
    client, a, *_ = env
    fake = FakeAnalyze(fail=RuntimeError("디코딩 실패"))
    fake.release.set()
    monkeypatch.setattr(vods_module, "analyze_vod", fake)
    vid = vod_id(a)

    client.post(f"/api/vods/{vid}/analyze", json={})
    job = wait_for(client, vid, "error")

    assert "디코딩 실패" in job["message"]


def test_idle_status_for_a_vod_without_a_job(env):
    client, a, *_ = env

    assert client.get(f"/api/vods/{vod_id(a)}/analyze").json()["state"] == "idle"


def test_missing_ffmpeg_blocks_analysis(env, monkeypatch):
    client, a, *_ = env
    monkeypatch.setattr(vods_module, "discover_ffmpeg", lambda: None)

    assert client.post(f"/api/vods/{vod_id(a)}/analyze", json={}).status_code == 503


def test_vod_wide_trash_restore_and_delete(env):
    client, a, _, vod_dir, *_ = env
    vid = vod_id(a)
    ids = [write_vod_clip(vod_dir, vid, 1, 10), write_vod_clip(vod_dir, vid, 2, 10)]
    other = write_vod_clip(vod_dir, "otherid00001", 1, 10)

    assert client.post(f"/api/vods/{vid}/trash").json()["count"] == 2
    assert all((vod_dir / ".trash" / f"{i}.json").exists() for i in ids)
    assert (vod_dir / f"{other}.json").exists()

    assert client.post(f"/api/vods/{vid}/restore").json()["count"] == 2
    assert all((vod_dir / f"{i}.json").exists() for i in ids)

    client.post(f"/api/vods/{vid}/trash")
    assert client.delete(f"/api/vods/{vid}/clips").json()["count"] == 2
    assert not list((vod_dir / ".trash").glob("*.json"))
    assert (vod_dir / f"{other}.json").exists()


def test_fs_videos_lists_folders_and_only_video_files(env):
    client, _, _, _, _, videos = env

    data = client.get("/api/fs/videos", params={"path": str(videos)}).json()

    assert data["dirs"] == ["sub"]
    assert [f["name"] for f in data["files"]] == ["a.mp4"]
    assert data["files"][0]["sizeBytes"] == 3000
    assert client.get("/api/fs/videos", params={"path": str(videos / "nope")}).status_code == 404
    assert client.get("/api/fs/videos").json()["dirs"]
