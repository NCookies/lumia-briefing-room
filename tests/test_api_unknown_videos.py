"""앱이 만들지 않은 영상(OBS 녹화 등)도 클립 폴더 안에 있으면 클립으로 보인다. (plan-fullvideo.md §3.9)"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api import app as app_module
from lumia_briefing_room.api import unknown_clips
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig, resolve_paths
from lumia_briefing_room.pipeline import delete_helper
from lumia_briefing_room.pipeline.clip_files import content_fingerprint


@pytest.fixture
def env(tmp_path, monkeypatch):
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", vod_clips=tmp_path / "vod", temp=tmp_path / "tmp"))
    resolved = resolve_paths(cfg.paths)
    monkeypatch.setattr(unknown_clips, "probe_duration", lambda path, ffmpeg: 123.5)
    monkeypatch.setattr(app_module, "discover_ffmpeg", lambda: Path("ffmpeg"))
    monkeypatch.setattr(delete_helper, "_send2trash", lambda p: Path(p).unlink())
    client = TestClient(create_app(cfg, config_path=tmp_path / "config.json"))
    client.videos, client.library = resolved.clips_steam, resolved.library_steam
    video = client.videos / "OBS" / "2026-09-30 방송.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"obs recording bytes" * 100)
    client.video = video
    client.uid = f"x_{content_fingerprint(video)}"
    return client


def test_default_list_does_not_include_unknown_videos_but_all_and_other_do(env):
    assert env.get("/api/clips").json() == []
    assert env.get("/api/clips", params={"source": "vod"}).json() == []
    for source in ("all", "other"):
        (clip,) = env.get("/api/clips", params={"source": source}).json()
        assert clip["id"] == env.uid and clip["title"] == "2026-09-30 방송"
        assert clip["source"] == "other" and clip["unknownVideo"] is True
        assert clip["durationSec"] == 123.5 and clip["sizeBytes"] == env.video.stat().st_size


def test_unknown_video_can_be_fetched_and_played(env):
    assert env.get(f"/api/clips/{env.uid}").json()["title"] == "2026-09-30 방송"
    resp = env.get(f"/api/clips/{env.uid}/video", headers={"range": "bytes=0-9"})
    assert resp.status_code == 206 and resp.content == env.video.read_bytes()[:10]
    assert env.get("/api/clips/x_unknown").status_code == 404


def test_thumbnail_is_made_on_first_view_and_cached(env, monkeypatch):
    calls = []

    def fake_thumbnail(clip, out, **kw):
        calls.append(clip)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"jpg")

    monkeypatch.setattr(unknown_clips, "make_thumbnail", fake_thumbnail)
    assert env.get(f"/api/clips/{env.uid}/thumbnail").content == b"jpg"
    assert env.get(f"/api/clips/{env.uid}/thumbnail").status_code == 200
    assert calls == [env.video], "두 번째부터는 캐시를 쓴다"


def test_editing_an_unknown_video_makes_info_that_survives_renames(env):
    resp = env.patch(f"/api/clips/{env.uid}", json={"title": "내 방송 하이라이트", "userLabel": "pvp"})
    assert resp.status_code == 200
    saved = json.loads((env.library / f"{env.uid}.json").read_text(encoding="utf-8"))
    assert saved["title"] == "내 방송 하이라이트" and "unknownVideo" not in saved and saved["videoFingerprint"]
    renamed = env.videos / "정리" / "이름 바꿈.mp4"
    renamed.parent.mkdir()
    env.video.rename(renamed)
    (clip,) = env.get("/api/clips", params={"source": "all"}).json()
    assert clip["title"] == "내 방송 하이라이트" and clip["userLabel"] == "pvp" and clip.get("unknownVideo") is None
    assert env.get(f"/api/clips/{env.uid}/video", headers={"range": "bytes=0-0"}).status_code == 206


def test_deleting_an_unknown_video_removes_the_file(env):
    assert env.delete(f"/api/clips/{env.uid}").status_code == 200
    assert not env.video.exists()
    assert env.get("/api/clips", params={"source": "all"}).json() == []


def test_unknown_videos_cannot_be_trimmed_or_split(env):
    assert env.post(f"/api/clips/{env.uid}/trim", json={"start": 1, "end": 5}).status_code == 409
    assert env.post(f"/api/clips/{env.uid}/split", json={"ranges": [{"start": 0, "end": 5}]}).status_code == 409


def test_export_works_for_unknown_videos(env, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    body = env.post(f"/api/clips/{env.uid}/export", json={"dir": str(out), "filename": "내보낸 영상"}).json()
    assert Path(body["path"]).read_bytes() == env.video.read_bytes()
