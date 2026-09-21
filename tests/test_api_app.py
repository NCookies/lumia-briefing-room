import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig


def _write_clip(clips_dir: Path, clip_id: str, *, video: bytes = b"fake video bytes 0123456789", **meta_overrides):
    clips_dir.mkdir(parents=True, exist_ok=True)
    (clips_dir / f"{clip_id}.mp4").write_bytes(video)
    thumbs = clips_dir / ".thumbs"
    thumbs.mkdir(exist_ok=True)
    thumb_path = thumbs / f"{clip_id}.jpg"
    thumb_path.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
    meta = {
        "title": clip_id, "tags": ["kill"], "dayNight": "day", "gameMode": "battle_royale",
        "pinned": False, "deletedAt": None, "thumbnailPath": str(thumb_path),
        **meta_overrides,
    }
    (clips_dir / f"{clip_id}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def client(tmp_path):
    clips_dir = tmp_path / "clips"
    cfg = Config(paths=PathsConfig(clips=clips_dir, temp=tmp_path / "tmp"))
    config_path = tmp_path / "config.json"
    app = create_app(cfg, config_path=config_path)
    app.state.clips_dir_for_test = clips_dir  # 테스트 편의
    return TestClient(app)


def test_list_clips_empty(client):
    resp = client.get("/api/clips")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_clips_returns_written_clips(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a")
    _write_clip(clips_dir, "b")

    resp = client.get("/api/clips")

    assert resp.status_code == 200
    ids = {c["id"] for c in resp.json()}
    assert ids == {"a", "b"}


def test_list_clips_filters_by_tag(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", tags=["kill"])
    _write_clip(clips_dir, "b", tags=["death"])

    resp = client.get("/api/clips", params={"tags": "death"})

    ids = {c["id"] for c in resp.json()}
    assert ids == {"b"}


def test_list_clips_excludes_trashed_by_default(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a")
    _write_clip(clips_dir, "b", deletedAt="2026-01-01T00:00:00+00:00")

    resp = client.get("/api/clips")

    ids = {c["id"] for c in resp.json()}
    assert ids == {"a"}


def test_get_one_clip(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", title="제목")

    resp = client.get("/api/clips/a")

    assert resp.status_code == 200
    assert resp.json()["title"] == "제목"


def test_get_missing_clip_404(client):
    resp = client.get("/api/clips/nope")
    assert resp.status_code == 404


def test_patch_title(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", title="old")

    resp = client.patch("/api/clips/a", json={"title": "new"})

    assert resp.status_code == 200
    assert resp.json()["title"] == "new"
    assert json.loads((clips_dir / "a.json").read_text(encoding="utf-8"))["title"] == "new"


def test_patch_pinned(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", pinned=False)

    resp = client.patch("/api/clips/a", json={"pinned": True})

    assert resp.status_code == 200
    assert resp.json()["pinned"] is True


def test_patch_missing_clip_404(client):
    resp = client.patch("/api/clips/nope", json={"title": "x"})
    assert resp.status_code == 404


def test_trash_and_restore_roundtrip(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a")

    trash_resp = client.post("/api/clips/a/trash")
    assert trash_resp.status_code == 200
    assert not (clips_dir / "a.json").exists()
    assert (clips_dir / ".trash" / "a.json").exists()

    list_resp = client.get("/api/clips", params={"trashed": "true"})
    assert [c["id"] for c in list_resp.json()] == ["a"]

    restore_resp = client.post("/api/clips/a/restore")
    assert restore_resp.status_code == 200
    assert (clips_dir / "a.json").exists()


def test_trash_missing_clip_404(client):
    resp = client.post("/api/clips/nope/trash")
    assert resp.status_code == 404


def test_delete_rejects_non_trashed_clip(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a")

    resp = client.delete("/api/clips/a")

    assert resp.status_code == 400
    assert (clips_dir / "a.json").exists()


def test_delete_removes_trashed_clip_permanently(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a")
    client.post("/api/clips/a/trash")

    resp = client.delete("/api/clips/a")

    assert resp.status_code == 200
    assert not (clips_dir / ".trash" / "a.json").exists()
    assert not (clips_dir / ".trash" / "a.mp4").exists()


def test_video_full_request(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", video=b"0123456789")

    resp = client.get("/api/clips/a/video")

    assert resp.status_code == 200
    assert resp.content == b"0123456789"
    assert resp.headers["accept-ranges"] == "bytes"


def test_video_range_request(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", video=b"0123456789")

    resp = client.get("/api/clips/a/video", headers={"Range": "bytes=2-5"})

    assert resp.status_code == 206
    assert resp.content == b"2345"
    assert resp.headers["content-range"] == "bytes 2-5/10"
    assert resp.headers["content-length"] == "4"


def test_video_range_open_ended(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", video=b"0123456789")

    resp = client.get("/api/clips/a/video", headers={"Range": "bytes=7-"})

    assert resp.status_code == 206
    assert resp.content == b"789"
    assert resp.headers["content-range"] == "bytes 7-9/10"


def test_video_missing_clip_404(client):
    resp = client.get("/api/clips/nope/video")
    assert resp.status_code == 404


def test_thumbnail_serves_image(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a")

    resp = client.get("/api/clips/a/thumbnail")

    assert resp.status_code == 200
    assert resp.content == b"\xff\xd8\xff\xe0fakejpeg"


def test_get_config_returns_defaults(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["filter"]["preset"] == "all"


def test_put_config_persists(client, tmp_path):
    new_cfg = {"filter": {"preset": "won"}}
    resp = client.put("/api/config", json=new_cfg)
    assert resp.status_code == 200

    resp2 = client.get("/api/config")
    assert resp2.json()["filter"]["preset"] == "won"


def test_patch_user_label_accepts_pvp_pve_and_null(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a")

    assert client.patch("/api/clips/a", json={"userLabel": "pvp"}).json()["userLabel"] == "pvp"
    assert client.patch("/api/clips/a", json={"userLabel": "pve"}).json()["userLabel"] == "pve"
    assert client.patch("/api/clips/a", json={"userLabel": None}).json()["userLabel"] is None
    assert json.loads((clips_dir / "a.json").read_text(encoding="utf-8"))["userLabel"] is None


def test_patch_user_label_rejects_other_values(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a")

    resp = client.patch("/api/clips/a", json={"userLabel": "maybe"})

    assert resp.status_code == 400


def test_list_clips_supports_score_label_and_sort_params(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", pvpScore=0.2)
    _write_clip(clips_dir, "b", pvpScore=1.0, userLabel="pvp")
    _write_clip(clips_dir, "c", pvpScore=0.6)

    ranked = client.get("/api/clips", params={"sort": "pvp"}).json()
    assert [c["id"] for c in ranked] == ["b", "c", "a"]

    strong = client.get("/api/clips", params={"minPvpScore": "0.5", "sort": "pvp"}).json()
    assert [c["id"] for c in strong] == ["b", "c"]

    unlabeled = client.get("/api/clips", params={"label": "unlabeled", "sort": "pvp"}).json()
    assert [c["id"] for c in unlabeled] == ["c", "a"]


def test_patching_a_label_marks_it_as_a_user_label_and_clears_the_conflict_flag(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", userLabel="pvp", labelSource="migrated", labelConflict=True)

    data = client.patch("/api/clips/a", json={"userLabel": "pve"}).json()

    assert data["labelSource"] == "user"
    assert data["labelConflict"] is False


def test_label_filter_conflict_lists_only_migrated_labels_that_need_a_look(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", userLabel="pvp", labelConflict=True)
    _write_clip(clips_dir, "b", userLabel="pvp", labelConflict=False)
    _write_clip(clips_dir, "c")

    ids = [c["id"] for c in client.get("/api/clips", params={"label": "conflict"}).json()]

    assert ids == ["a"]


def test_fs_dirs_lists_only_subdirectories_sorted(client, tmp_path):
    base = tmp_path / "replay"
    (base / "b").mkdir(parents=True)
    (base / "a").mkdir()
    (base / "file.txt").write_text("x")

    resp = client.get("/api/fs/dirs", params={"path": str(base)})

    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == str(base)
    assert body["parent"] == str(tmp_path)
    assert body["dirs"] == ["a", "b"]


def test_fs_dirs_without_path_lists_drives_or_roots(client):
    body = client.get("/api/fs/dirs").json()

    assert body["path"] == ""
    assert body["parent"] is None
    assert body["dirs"]


def test_fs_dirs_missing_path_is_404(client, tmp_path):
    assert client.get("/api/fs/dirs", params={"path": str(tmp_path / "nope")}).status_code == 404


def test_fs_mkdir_creates_folder(client, tmp_path):
    resp = client.post("/api/fs/mkdir", json={"path": str(tmp_path), "name": "레니"})

    assert resp.status_code == 200
    assert (tmp_path / "레니").is_dir()
    assert resp.json()["path"] == str(tmp_path / "레니")


def test_fs_mkdir_rejects_path_separators(client, tmp_path):
    resp = client.post("/api/fs/mkdir", json={"path": str(tmp_path), "name": "a/b"})

    assert resp.status_code == 400


def test_export_copies_video_and_remembers_folder(client, tmp_path):
    _write_clip(client.app.state.clips_dir_for_test, "a", title="멋진 킬", video=b"VIDEO")
    dest = tmp_path / "replay" / "레니"
    dest.mkdir(parents=True)

    resp = client.post("/api/clips/a/export", json={"dir": str(dest)})

    assert resp.status_code == 200
    saved = Path(resp.json()["path"])
    assert saved == dest / "멋진 킬.mp4"
    assert saved.read_bytes() == b"VIDEO"
    assert client.get("/api/config").json()["paths"]["exportDefault"] == str(dest)
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["paths"]["exportDefault"] == str(dest)


def test_export_uses_given_filename_sanitized_and_never_overwrites(client, tmp_path):
    _write_clip(client.app.state.clips_dir_for_test, "a", video=b"NEW")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "x_y.mp4").write_bytes(b"OLD")

    resp = client.post("/api/clips/a/export", json={"dir": str(tmp_path / "out"), "filename": 'x:y'})

    assert Path(resp.json()["path"]).name == "x_y (2).mp4"
    assert (tmp_path / "out" / "x_y.mp4").read_bytes() == b"OLD"


def test_export_missing_dir_or_clip_is_404(client, tmp_path):
    _write_clip(client.app.state.clips_dir_for_test, "a")

    assert client.post("/api/clips/a/export", json={"dir": str(tmp_path / "nope")}).status_code == 404
    (tmp_path / "out").mkdir()
    assert client.post("/api/clips/zzz/export", json={"dir": str(tmp_path / "out")}).status_code == 404


def test_config_includes_player_nickname_and_can_be_updated(client, tmp_path):
    assert client.get("/api/config").json()["player"]["nickname"] == ""

    resp = client.put("/api/config", json={"player": {"nickname": "東京タワー"}})

    assert resp.json()["player"]["nickname"] == "東京タワー"
    assert client.get("/api/config").json()["player"]["nickname"] == "東京タワー"


def test_config_reads_changes_made_to_the_file_by_another_writer(client, tmp_path):
    from lumia_briefing_room.config import Config, PlayerConfig, save_config

    save_config(Config(player=PlayerConfig(nickname="워처가학습")), tmp_path / "config.json")

    assert client.get("/api/config").json()["player"]["nickname"] == "워처가학습"
    client.put("/api/config", json={"paths": {"exportDefault": str(tmp_path)}})
    assert client.get("/api/config").json()["player"]["nickname"] == "워처가학습"
