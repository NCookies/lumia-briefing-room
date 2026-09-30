"""클립 정리 탭 API: 클립 폴더를 실제 폴더 구조 그대로 다룬다. (plan-fullvideo.md §3.9)"""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api import clip_index, library_routes, unknown_clips
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig, resolve_paths
from lumia_briefing_room.pipeline import delete_helper
from tests_helpers_mp4 import mp4_with_comment


def _fake_trash(path):
    path = Path(path)
    if path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def make_client(tmp_path, monkeypatch, *, new_layout: bool):
    if new_layout:
        paths = PathsConfig(root=tmp_path / "store", temp=tmp_path / "tmp")
    else:
        paths = PathsConfig(clips=tmp_path / "clips", vod_clips=tmp_path / "vod", temp=tmp_path / "tmp")
    cfg = Config(paths=paths)
    resolved = resolve_paths(cfg.paths)
    monkeypatch.setattr(unknown_clips, "probe_duration", lambda path, ffmpeg: 10.0)
    monkeypatch.setattr(clip_index, "discover_ffmpeg", lambda: None)
    monkeypatch.setattr(delete_helper, "_send2trash", _fake_trash)
    client = TestClient(create_app(cfg, config_path=tmp_path / "config.json"))
    client.resolved = resolved
    return client


@pytest.fixture
def client(tmp_path, monkeypatch):
    return make_client(tmp_path, monkeypatch, new_layout=True)


def add_clip(client, clip_id, folder="스팀 녹화", uid=None, **meta):
    base = client.resolved.clips_root / folder if folder else client.resolved.clips_root
    base.mkdir(parents=True, exist_ok=True)
    uid = uid or f"uid-{clip_id}"
    video = base / f"{clip_id}.mp4"
    video.write_bytes(mp4_with_comment(f"lumia:clipUid={uid}") + b"0123456789")
    lib = client.resolved.library_steam
    lib.mkdir(parents=True, exist_ok=True)
    body = {"title": f"제목 {clip_id}", "clipUid": uid, "tags": ["kill"], **meta}
    (lib / f"{clip_id}.json").write_text(json.dumps(body), encoding="utf-8")
    return video


def listing(client, path=""):
    resp = client.get("/api/library", params={"path": path})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_lists_folders_and_clips_of_the_real_folder(client):
    add_clip(client, "a")
    add_clip(client, "b", folder="캐릭터/아야")
    top = listing(client)
    assert top["layout"] == "new" and top["virtualTop"] is False
    assert [f["name"] for f in top["folders"]] == ["스팀 녹화", "캐릭터"]
    assert top["clips"] == []
    inner = listing(client, "스팀 녹화")
    assert [c["id"] for c in inner["clips"]] == ["a"]
    assert inner["clips"][0]["title"] == "제목 a" and inner["clips"][0]["relPath"] == "스팀 녹화/a.mp4"
    assert [c["name"] for c in listing(client, "캐릭터/아야")["crumbs"]] == ["클립", "캐릭터", "아야"]


def test_unknown_videos_are_listed_too(client):
    base = client.resolved.clips_root / "스팀 녹화"
    base.mkdir(parents=True)
    (base / "OBS 녹화.mp4").write_bytes(b"obs" * 100)
    (clip,) = listing(client, "스팀 녹화")["clips"]
    assert clip["title"] == "OBS 녹화" and clip["unknownVideo"] is True


def test_unsafe_paths_are_rejected(client):
    for bad in ("..", "../x", "/abs", ".cache"):
        assert client.get("/api/library", params={"path": bad}).status_code == 400
    assert client.get("/api/library", params={"path": "없는 폴더"}).status_code == 404


def test_create_rename_and_move(client):
    add_clip(client, "a")
    assert client.post("/api/library/folders", json={"path": "", "name": "아야 모음"}).json() == {"path": "아야 모음"}
    assert client.post("/api/library/folders", json={"path": "", "name": "아야 모음"}).status_code == 409
    assert client.post("/api/library/folders", json={"path": "", "name": "a/b"}).status_code == 400
    moved = client.post("/api/library/move", json={"items": ["스팀 녹화/a.mp4"], "dest": "아야 모음"}).json()
    assert moved == {"moved": ["아야 모음/a.mp4"]}
    renamed = client.patch("/api/library/rename", json={"path": "아야 모음/a.mp4", "name": "내 클립"}).json()
    assert renamed == {"path": "아야 모음/내 클립.mp4"}
    (clip,) = listing(client, "아야 모음")["clips"]
    assert clip["id"] == "a" and clip["title"] == "제목 a" and clip["fileName"] == "내 클립.mp4"
    assert client.get("/api/clips/a/video", headers={"range": "bytes=0-0"}).status_code == 206


def test_move_conflict_changes_nothing(client):
    add_clip(client, "a")
    add_clip(client, "a2", folder="대상")
    (client.resolved.clips_root / "대상" / "a.mp4").write_bytes(b"other")
    r = client.post("/api/library/move", json={"items": ["스팀 녹화/a.mp4"], "dest": "대상"})
    assert r.status_code == 409
    assert (client.resolved.clips_root / "스팀 녹화" / "a.mp4").exists()


def test_the_clip_keeps_its_info_after_being_moved_in_explorer_style(client):
    video = add_clip(client, "a", userLabel="pvp")
    target = client.resolved.clips_root / "탐색기로 옮김" / "완전히 다른 이름.mp4"
    target.parent.mkdir()
    video.rename(target)
    (clip,) = listing(client, "탐색기로 옮김")["clips"]
    assert clip["id"] == "a" and clip["userLabel"] == "pvp"


def test_delete_removes_videos_info_and_folders(client):
    v1 = add_clip(client, "a")
    add_clip(client, "b", folder="캐릭터")
    (client.resolved.clips_root / "캐릭터" / "메모.txt").write_text("내 파일", encoding="utf-8")
    r = client.post("/api/library/delete", json={"items": ["스팀 녹화/a.mp4", "캐릭터"]})
    assert r.json() == {"deleted": 2}
    assert not v1.exists() and not (client.resolved.clips_root / "캐릭터").exists()
    assert not (client.resolved.library_steam / "a.json").exists()
    assert not (client.resolved.library_steam / "b.json").exists()


def test_deleting_one_copy_keeps_the_info_for_the_other_copy(client):
    a = add_clip(client, "a", uid="same")
    copy = client.resolved.clips_root / "백업" / "a 복사본.mp4"
    copy.parent.mkdir()
    copy.write_bytes(a.read_bytes())
    client.post("/api/library/delete", json={"items": ["백업/a 복사본.mp4"]})
    assert a.exists() and not copy.exists()
    assert (client.resolved.library_steam / "a.json").exists()


def test_the_clip_folder_itself_cannot_be_deleted(client):
    assert client.post("/api/library/delete", json={"items": [""]}).status_code == 400


def test_batch_export_copies_the_videos(client, tmp_path):
    add_clip(client, "a")
    add_clip(client, "b", folder="캐릭터")
    out = tmp_path / "out"
    out.mkdir()
    body = client.post("/api/library/export", json={"items": ["스팀 녹화", "캐릭터/b.mp4"], "dir": str(out)}).json()
    assert sorted(Path(p).name for p in body["paths"]) == ["a.mp4", "b.mp4"]
    bad = client.post("/api/library/export", json={"items": ["스팀 녹화"], "dir": str(tmp_path / "nope")})
    assert bad.status_code == 404


def test_reveal_opens_explorer_on_windows(client, monkeypatch):
    add_clip(client, "a")
    opened = []
    monkeypatch.setattr(library_routes.subprocess, "Popen", lambda args: opened.append(args))
    monkeypatch.setattr(library_routes.os, "name", "nt")
    assert client.post("/api/library/reveal", json={"path": "스팀 녹화/a.mp4"}).status_code == 200
    assert opened and opened[0][0] == "explorer" and opened[0][1].startswith("/select,")


def test_legacy_layout_has_a_virtual_top(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch, new_layout=False)
    c.resolved.clips_steam.mkdir(parents=True)
    c.resolved.clips_vod.mkdir(parents=True)
    (c.resolved.clips_steam / "x.mp4").write_bytes(b"v" * 50)
    top = listing(c)
    assert top["layout"] == "legacy" and top["virtualTop"] is True
    assert [f["name"] for f in top["folders"]] == ["스팀 녹화", "영상 파일"]
    assert [x["fileName"] for x in listing(c, "스팀 녹화")["clips"]] == ["x.mp4"]
    assert c.post("/api/library/folders", json={"path": "", "name": "새"}).status_code == 400
    assert c.post("/api/library/delete", json={"items": ["스팀 녹화"]}).status_code == 400
