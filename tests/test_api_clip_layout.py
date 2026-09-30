"""클립 정보는 앱 데이터 library, 영상은 저장 폴더(하위 폴더 포함)에 따로 있을 때 기존 클립 API 가 영상을 제자리에서 다룬다."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api import app as app_module
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig, resolve_paths
from lumia_briefing_room.pipeline import delete_helper, trim as trim_module


@pytest.fixture
def env(tmp_path):
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", vod_clips=tmp_path / "vod", temp=tmp_path / "tmp"))
    resolved = resolve_paths(cfg.paths)
    client = TestClient(create_app(cfg, config_path=tmp_path / "config.json"))
    client.library, client.videos = resolved.library_steam, resolved.clips_steam
    client.tmp = tmp_path
    return client


def add_clip(env, clip_id, *, folder="캐릭터/아야", **meta):
    video_dir = env.videos / folder if folder else env.videos
    video_dir.mkdir(parents=True, exist_ok=True)
    (video_dir / f"{clip_id}.mp4").write_bytes(b"0123456789")
    env.library.mkdir(parents=True, exist_ok=True)
    body = {"title": clip_id, "tags": ["kill"], "durationSec": 20.0, **meta}
    (env.library / f"{clip_id}.json").write_text(json.dumps(body), encoding="utf-8")
    return video_dir / f"{clip_id}.mp4"


def test_list_and_video_find_a_clip_in_a_subfolder(env):
    add_clip(env, "a")
    (clip,) = env.get("/api/clips").json()
    assert clip["id"] == "a" and clip["sizeBytes"] == 10
    assert env.get("/api/clips/a/video").content == b"0123456789"


def test_delete_removes_the_video_from_its_subfolder(env, monkeypatch):
    monkeypatch.setattr(delete_helper, "_send2trash", lambda p: Path(p).unlink())
    video = add_clip(env, "a")
    assert env.delete("/api/clips/a").status_code == 200
    assert not video.exists() and not (env.library / "a.json").exists()


def test_export_copies_the_video_from_its_subfolder(env):
    add_clip(env, "a")
    out = env.tmp / "out"
    out.mkdir()
    body = env.post("/api/clips/a/export", json={"dir": str(out), "filename": "내 클립"}).json()
    assert Path(body["path"]).read_bytes() == b"0123456789"


def test_trim_rewrites_the_video_in_place(env, monkeypatch):
    video = add_clip(env, "a")
    seen = []

    def fake_run(cmd, **kw):
        seen.append(cmd)
        Path(cmd[-1]).write_bytes(b"trimmed")

    monkeypatch.setattr(trim_module, "run_hidden", fake_run)
    monkeypatch.setattr(app_module, "discover_ffmpeg", lambda: Path("ffmpeg"))
    assert env.post("/api/clips/a/trim", json={"start": 2, "end": 12}).status_code == 200
    assert video.read_bytes() == b"trimmed"
    assert Path(seen[0][-1]).parent == video.parent, "임시 파일도 영상 옆(같은 드라이브)에 만든다"
    assert not list(video.parent.glob("*.trim.mp4"))


def test_split_creates_pieces_next_to_the_original_video(env, monkeypatch):
    video = add_clip(env, "a")
    monkeypatch.setattr(delete_helper, "_send2trash", lambda p: Path(p).unlink())
    monkeypatch.setattr(trim_module, "run_hidden", lambda cmd, **kw: Path(cmd[-1]).write_bytes(b"piece"))
    monkeypatch.setattr(app_module, "discover_ffmpeg", lambda: Path("ffmpeg"))
    body = env.post("/api/clips/a/split", json={"ranges": [{"start": 0, "end": 5}, {"start": 8, "end": 15}]})
    assert body.status_code == 200
    assert sorted(p.name for p in video.parent.glob("*.mp4")) == ["a-p1.mp4", "a-p2.mp4"]
    assert sorted(p.name for p in env.library.glob("*.json")) == ["a-p1.json", "a-p2.json"]
    assert not video.exists()
    assert {c["id"] for c in env.get("/api/clips").json()} == {"a-p1", "a-p2"}
