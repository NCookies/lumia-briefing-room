import json
import threading

from fastapi.testclient import TestClient

from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.api.clip_uid_startup import backfill_clip_uids_locked, start_backfill_thread
from lumia_briefing_room.config import Config, PathsConfig, resolve_paths


def write_clip(root, clip_id, **meta):
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{clip_id}.mp4").write_bytes(b"x")
    data = {"title": clip_id, "tags": [], "pinned": False, "deletedAt": None, "durationSec": 5.0, **meta}
    (root / f"{clip_id}.json").write_text(json.dumps(data), encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _cfg(tmp_path):
    return Config(paths=PathsConfig(clips=tmp_path / "clips", vod_clips=tmp_path / "vod", temp=tmp_path / "tmp"))


def steam_lib(tmp_path):
    return resolve_paths(_cfg(tmp_path).paths).library_steam


def make_app(tmp_path):
    return create_app(_cfg(tmp_path), config_path=tmp_path / "c.json")


def test_listing_clips_fills_a_missing_clip_uid_as_a_safety_net(tmp_path):
    write_clip(steam_lib(tmp_path), "a")
    write_clip(steam_lib(tmp_path), "b", clipUid="k" * 32)
    resp = TestClient(make_app(tmp_path)).get("/api/clips")
    assert resp.status_code == 200
    assert len(read(steam_lib(tmp_path) / "a.json")["clipUid"]) == 32
    assert read(steam_lib(tmp_path) / "b.json")["clipUid"] == "k" * 32


def test_startup_backfill_covers_both_clip_folders_and_is_repeatable(tmp_path):
    lib = resolve_paths(_cfg(tmp_path).paths)
    write_clip(lib.library_steam, "a")
    write_clip(lib.library_vod, "vod_x_g01_000001")
    write_clip(lib.library_steam / ".trash", "t")
    app = make_app(tmp_path)

    assert backfill_clip_uids_locked(app) == 3
    first = read(lib.library_steam / "a.json")["clipUid"]
    assert backfill_clip_uids_locked(app) == 0
    assert read(lib.library_steam / "a.json")["clipUid"] == first


def test_startup_backfill_takes_the_same_lock_the_api_uses(tmp_path):
    write_clip(steam_lib(tmp_path), "a")
    app = make_app(tmp_path)
    finished = threading.Event()

    with app.state.lock:
        thread = start_backfill_thread(app, on_done=finished.set)
        assert not finished.wait(0.3)
    assert finished.wait(5)
    thread.join(5)
    assert "clipUid" in read(steam_lib(tmp_path) / "a.json")


def test_startup_backfill_never_raises_when_folders_do_not_exist(tmp_path):
    assert backfill_clip_uids_locked(make_app(tmp_path)) == 0


def test_api_requests_are_counted_so_the_app_can_tell_whether_a_page_is_alive(tmp_path):
    app = make_app(tmp_path)
    client = TestClient(app)
    assert app.state.request_count == 0
    client.get("/api/app-info")
    client.get("/api/app-info")
    client.get("/")
    assert app.state.request_count == 2
