import json
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api import app as app_module
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig
from lumia_briefing_room.pipeline import proxy

from conftest import FFMPEG_PATH, requires_ffmpeg


def _write_clip(clips_dir: Path, clip_id: str, video: bytes = b"video", **meta) -> Path:
    clips_dir.mkdir(parents=True, exist_ok=True)
    (clips_dir / f"{clip_id}.mp4").write_bytes(video)
    body = {"title": clip_id, "tags": ["kill"], "durationSec": 4.0, "deletedAt": None, **meta}
    (clips_dir / f"{clip_id}.json").write_text(json.dumps(body), encoding="utf-8")
    return clips_dir / f"{clip_id}.mp4"


@pytest.fixture
def client(tmp_path):
    clips_dir = tmp_path / "clips"
    app = create_app(Config(paths=PathsConfig(clips=clips_dir, temp=tmp_path / "tmp")), config_path=tmp_path / "c.json")
    app.state.clips_dir_for_test = clips_dir
    return TestClient(app)


def _fake_create(calls):
    def create(ffmpeg, src, out, *, height, crf, duration_sec, on_progress=None):
        calls.append((src.name, height, crf, duration_sec))
        out.parent.mkdir(parents=True, exist_ok=True)
        if on_progress:
            on_progress(0.5)
        out.write_bytes(b"proxy-bytes")
        return "h264_mf"

    return create


def _wait_ready(client, clip_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/clips/{clip_id}/proxy").json()
        if body["state"] in ("ready", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("프록시가 제한 시간 안에 안 끝났다")


def test_status_is_none_before_anything(client):
    _write_clip(client.app.state.clips_dir_for_test, "a")
    assert client.get("/api/clips/a/proxy").json() == {"state": "none", "progress": 0.0}


def test_proxy_unknown_clip_is_404(client):
    assert client.get("/api/clips/zzz/proxy").status_code == 404
    assert client.post("/api/clips/zzz/proxy").status_code == 404
    assert client.get("/api/clips/zzz/video", params={"proxy": 1}).status_code == 404


def test_post_builds_proxy_in_background_then_serves_it(client, monkeypatch):
    calls = []
    monkeypatch.setattr(app_module, "create_proxy", _fake_create(calls))
    monkeypatch.setattr(app_module, "discover_ffmpeg", lambda: Path("ffmpeg"))
    clips = client.app.state.clips_dir_for_test
    _write_clip(clips, "a", video=b"original hevc")

    started = client.post("/api/clips/a/proxy")
    assert started.status_code == 202
    assert _wait_ready(client, "a")["state"] == "ready"

    assert calls == [("a.mp4", 1080, 23, 4.0)]
    assert (clips / ".proxy" / "a.mp4").read_bytes() == b"proxy-bytes"
    served = client.get("/api/clips/a/video", params={"proxy": 1})
    assert served.status_code == 200 and served.content == b"proxy-bytes"
    assert client.get("/api/clips/a/video").content == b"original hevc"


def test_post_again_when_ready_does_not_rebuild(client, monkeypatch):
    calls = []
    monkeypatch.setattr(app_module, "create_proxy", _fake_create(calls))
    monkeypatch.setattr(app_module, "discover_ffmpeg", lambda: Path("ffmpeg"))
    _write_clip(client.app.state.clips_dir_for_test, "a")
    client.post("/api/clips/a/proxy")
    _wait_ready(client, "a")

    again = client.post("/api/clips/a/proxy")

    assert again.status_code == 200 and again.json()["state"] == "ready"
    assert len(calls) == 1


def test_video_proxy_before_ready_is_409(client):
    _write_clip(client.app.state.clips_dir_for_test, "a")
    assert client.get("/api/clips/a/video", params={"proxy": 1}).status_code == 409


def test_failed_build_is_reported_and_can_be_retried(client, monkeypatch):
    monkeypatch.setattr(app_module, "discover_ffmpeg", lambda: Path("ffmpeg"))

    def boom(*args, **kwargs):
        raise proxy.ProxyError("인코더 없음")

    monkeypatch.setattr(app_module, "create_proxy", boom)
    _write_clip(client.app.state.clips_dir_for_test, "a")
    client.post("/api/clips/a/proxy")
    body = _wait_ready(client, "a")
    assert body["state"] == "failed" and "인코더 없음" in body["message"]

    monkeypatch.setattr(app_module, "create_proxy", _fake_create([]))
    client.post("/api/clips/a/proxy")
    assert _wait_ready(client, "a")["state"] == "ready"


def test_post_without_ffmpeg_is_503(client, monkeypatch):
    monkeypatch.setattr(app_module, "discover_ffmpeg", lambda: None)
    _write_clip(client.app.state.clips_dir_for_test, "a")
    assert client.post("/api/clips/a/proxy").status_code == 503


def test_stale_proxy_after_original_changes_is_not_served(client, monkeypatch):
    import os

    monkeypatch.setattr(app_module, "create_proxy", _fake_create([]))
    monkeypatch.setattr(app_module, "discover_ffmpeg", lambda: Path("ffmpeg"))
    clips = client.app.state.clips_dir_for_test
    mp4 = _write_clip(clips, "a")
    client.post("/api/clips/a/proxy")
    _wait_ready(client, "a")

    future = time.time() + 100
    os.utime(mp4, (future, future))

    assert client.get("/api/clips/a/proxy").json()["state"] == "none"
    assert client.get("/api/clips/a/video", params={"proxy": 1}).status_code == 409


def test_permanent_delete_and_empty_trash_remove_the_proxy(client, monkeypatch):
    monkeypatch.setattr(app_module, "create_proxy", _fake_create([]))
    monkeypatch.setattr(app_module, "discover_ffmpeg", lambda: Path("ffmpeg"))
    clips = client.app.state.clips_dir_for_test
    for cid in ("a", "b"):
        _write_clip(clips, cid)
        client.post(f"/api/clips/{cid}/proxy")
        _wait_ready(client, cid)
        client.post(f"/api/clips/{cid}/trash")
    assert (clips / ".proxy" / "a.mp4").exists()

    client.delete("/api/clips/a")
    assert not (clips / ".proxy" / "a.mp4").exists()
    assert (clips / ".proxy" / "b.mp4").exists()

    client.post("/api/trash/empty")
    assert not (clips / ".proxy" / "b.mp4").exists()


def test_proxy_of_a_trashed_clip_can_still_be_built(client, monkeypatch):
    monkeypatch.setattr(app_module, "create_proxy", _fake_create([]))
    monkeypatch.setattr(app_module, "discover_ffmpeg", lambda: Path("ffmpeg"))
    clips = client.app.state.clips_dir_for_test
    _write_clip(clips, "a")
    client.post("/api/clips/a/trash")
    assert client.post("/api/clips/a/proxy").status_code == 202
    assert _wait_ready(client, "a")["state"] == "ready"
    assert client.get("/api/clips/a/video", params={"proxy": 1}).content == b"proxy-bytes"


@requires_ffmpeg
def test_end_to_end_with_real_ffmpeg(client):
    clips = client.app.state.clips_dir_for_test
    mp4 = clips / "a.mp4"
    clips.mkdir(parents=True, exist_ok=True)
    made = subprocess.run(
        [str(FFMPEG_PATH), "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
         "testsrc=size=320x180:rate=30:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mp4)],
        capture_output=True,
    )
    assert made.returncode == 0
    _write_clip(clips, "a", video=mp4.read_bytes(), durationSec=2.0)

    assert client.post("/api/clips/a/proxy").status_code == 202
    assert _wait_ready(client, "a", timeout=30)["state"] == "ready"
    served = client.get("/api/clips/a/video", params={"proxy": 1})
    assert served.status_code == 200 and len(served.content) > 1000
