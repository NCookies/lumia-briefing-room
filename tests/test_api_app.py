import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig, resolve_paths


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
    cfg = Config(paths=PathsConfig(clips=clips_dir, vod_clips=tmp_path / "vod", temp=tmp_path / "tmp"))
    config_path = tmp_path / "config.json"
    app = create_app(cfg, config_path=config_path)
    resolved = resolve_paths(cfg.paths)
    app.state.clips_dir_for_test = resolved.library_steam  # 테스트 편의: 클립 정보(library) 폴더, 영상은 그 옆에 둬도 찾는다
    app.state.video_dir_for_test = resolved.clips_steam
    app.state.games_dir_for_test = resolved.games_steam
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


def test_delete_missing_clip_404(client):
    resp = client.delete("/api/clips/nope")
    assert resp.status_code == 404


def test_delete_permanent_mode_removes_the_clip_files(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a")
    client.put("/api/config", json={"ui": {"deleteMode": "permanent"}})

    resp = client.delete("/api/clips/a")

    assert resp.status_code == 200
    assert resp.json() == {"id": "a", "deleted": True}
    assert not (clips_dir / "a.json").exists()
    assert not (clips_dir / "a.mp4").exists()
    assert not (clips_dir / ".thumbs" / "a.jpg").exists()


def test_delete_default_mode_sends_the_clip_to_the_recycle_bin(client, monkeypatch):
    from lumia_briefing_room.pipeline import delete_helper

    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a")
    sent = []
    monkeypatch.setattr(delete_helper, "_send2trash", lambda path: sent.append(Path(path).name))

    resp = client.delete("/api/clips/a")

    assert resp.status_code == 200
    assert set(sent) == {"a.json", "a.mp4", "a.jpg"}


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


def test_list_clips_filters_by_title_query(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", title="5일차 낮 Police Station KILL")
    _write_clip(clips_dir, "b", title="8일차 밤 초원")

    resp = client.get("/api/clips", params={"q": "  police   station kill "})

    assert [c["id"] for c in resp.json()] == ["a"]


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


def test_result_image_serves_the_games_result_screenshot(client, tmp_path):
    image = tmp_path / "r.jpg"
    image.write_bytes(b"\xff\xd8\xff\xe0resultjpeg")
    _write_clip(client.app.state.clips_dir_for_test, "a", matchResult={"placement": 4, "imagePath": str(image)})

    resp = client.get("/api/clips/a/result-image")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == image.read_bytes()


def test_result_image_is_404_without_image(client):
    _write_clip(client.app.state.clips_dir_for_test, "a")
    _write_clip(client.app.state.clips_dir_for_test, "b", matchResult={"placement": 4})

    assert client.get("/api/clips/a/result-image").status_code == 404
    assert client.get("/api/clips/b/result-image").status_code == 404
    assert client.get("/api/clips/zzz/result-image").status_code == 404


def test_character_portrait_serves_my_character_and_teammate_slots(client, tmp_path):
    clips_dir = client.app.state.clips_dir_for_test
    me = tmp_path / "me.jpg"
    me.write_bytes(b"\xff\xd8\xff\xe0me")
    mate1 = tmp_path / "mate1.jpg"
    mate1.write_bytes(b"\xff\xd8\xff\xe0mate1")
    _write_clip(
        clips_dir, "a",
        myCharacterPortraitPath=str(me),
        teammatePortraitPaths=[str(mate1)],
    )

    resp_me = client.get("/api/clips/a/character-portrait/me")
    resp_mate1 = client.get("/api/clips/a/character-portrait/teammate1")
    resp_mate2 = client.get("/api/clips/a/character-portrait/teammate2")

    assert resp_me.status_code == 200 and resp_me.content == me.read_bytes()
    assert resp_mate1.status_code == 200 and resp_mate1.content == mate1.read_bytes()
    assert resp_mate2.status_code == 404


def test_character_portrait_rejects_unknown_slot(client):
    _write_clip(client.app.state.clips_dir_for_test, "a")

    assert client.get("/api/clips/a/character-portrait/nope").status_code == 404


def test_patch_match_result_locks_placement_and_outcome_as_manual(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", matchResult={"placement": 4, "total": 8, "outcome": "실험 종료"})

    resp = client.patch("/api/clips/a", json={"matchResult": {"placement": 1, "outcome": "최종 생존"}})

    assert resp.status_code == 200
    body = resp.json()
    assert body["matchResult"] == {"placement": 1, "total": 8, "outcome": "최종 생존"}
    assert body["matchResultSource"] == "manual"
    saved = json.loads((clips_dir / "a.json").read_text(encoding="utf-8"))
    assert saved["matchResultSource"] == "manual"


def test_patch_match_result_rejects_unknown_fields(client):
    _write_clip(client.app.state.clips_dir_for_test, "a")

    resp = client.patch("/api/clips/a", json={"matchResult": {"character": "마커스"}})

    assert resp.status_code == 400


def test_patch_match_result_source_null_unlocks_without_changing_values(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", matchResult={"placement": 1}, matchResultSource="manual")

    resp = client.patch("/api/clips/a", json={"matchResultSource": None})

    assert resp.status_code == 200
    body = resp.json()
    assert body["matchResultSource"] is None
    assert body["matchResult"] == {"placement": 1}


def _enable_cleanup(client, **retention):
    client.put("/api/config", json={"retention": {"autoCleanEnabled": True, **retention}})


def _write_game(client, key, *, start, size=100, pinned=False):
    import json

    games = client.app.state.games_dir_for_test
    folder = games / key
    folder.mkdir(parents=True)
    (folder / "full.mp4").write_bytes(b"x" * size)
    (folder / "game.json").write_text(
        json.dumps({"gameKey": key, "matchStartUtc": start, "pinned": pinned, "candidates": [],
                    "fullVideo": {"path": "full.mp4", "sizeBytes": size}}),
        encoding="utf-8",
    )
    return folder


def test_cleanup_preview_counts_without_touching_files(client):
    old = _write_game(client, "old", start="2020-01-01T00:00:00Z")
    _write_game(client, "new", start="2999-01-01T00:00:00Z")
    _enable_cleanup(client, maxAgeDays=30)

    resp = client.post("/api/cleanup", json={"dryRun": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["toDelete"] == 1 and body["applied"] is False
    assert (old / "full.mp4").exists()


def test_cleanup_run_deletes_old_full_videos_but_keeps_the_game_record_and_clips(client):
    clips = client.app.state.clips_dir_for_test
    _write_clip(clips, "clip", matchStartUtc="2020-01-01T00:00:00Z")
    old = _write_game(client, "old", start="2020-01-01T00:00:00Z")
    _enable_cleanup(client, maxAgeDays=30, deleteMode="permanent")

    body = client.post("/api/cleanup", json={}).json()

    assert body["toDelete"] == 1 and body["applied"] is True
    assert not (old / "full.mp4").exists()
    assert (old / "game.json").exists()
    assert (clips / "clip.json").exists()


def test_cleanup_does_nothing_when_disabled(client):
    old = _write_game(client, "old", start="2020-01-01T00:00:00Z")
    client.put("/api/config", json={"retention": {"autoCleanEnabled": False, "maxAgeDays": 30}})

    body = client.post("/api/cleanup", json={}).json()

    assert body["toDelete"] == 0
    assert (old / "full.mp4").exists()


def test_cleanup_preview_endpoint_returns_reason_and_due_date_per_game(client):
    from lumia_briefing_room.pipeline.cleanup_registry import registry as cleanup_preview_registry

    _write_game(client, "old", start="2020-01-01T00:00:00Z")
    _write_game(client, "new", start="2999-01-01T00:00:00Z")
    _enable_cleanup(client, maxAgeDays=30)
    cleanup_preview_registry.recompute_now()  # 디바운스를 기다리지 않고 바로 계산

    resp = client.get("/api/cleanup/preview")

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"old"}
    assert body["old"]["reason"] == "age"
    assert body["old"]["dueAt"] is not None


def test_cleanup_preview_skips_pinned_games(client):
    from lumia_briefing_room.pipeline.cleanup_registry import registry as cleanup_preview_registry

    _write_game(client, "old", start="2020-01-01T00:00:00Z", pinned=True)
    _enable_cleanup(client, maxAgeDays=30)
    cleanup_preview_registry.recompute_now()

    assert client.get("/api/cleanup/preview").json() == {}


def test_retention_limits_can_be_cleared_with_null(client):
    client.put("/api/config", json={"retention": {"maxAgeDays": 30}})

    resp = client.put("/api/config", json={"retention": {"maxAgeDays": None}})

    assert resp.json()["retention"]["maxAgeDays"] is None


def test_list_clips_includes_size_bytes(client):
    _write_clip(client.app.state.clips_dir_for_test, "a", video=b"x" * 1234)

    assert client.get("/api/clips").json()[0]["sizeBytes"] == 1234


def test_permanently_deleting_the_last_clip_of_a_game_removes_its_result_image(client, tmp_path):
    clips = client.app.state.clips_dir_for_test
    client.put("/api/config", json={"ui": {"deleteMode": "permanent"}})
    image = clips / ".thumbs" / "20260920_100000_result.jpg"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"j")
    _write_clip(clips, "a", matchResult={"imagePath": str(image)})
    _write_clip(clips, "b", matchResult={"imagePath": str(image)})

    client.delete("/api/clips/a")
    assert image.exists()

    client.delete("/api/clips/b")
    assert not image.exists()


def test_trim_rejects_an_invalid_range_and_unknown_clip(client):
    _write_clip(client.app.state.clips_dir_for_test, "a", durationSec=20.0)

    assert client.post("/api/clips/a/trim", json={"start": 5, "end": 5}).status_code == 400
    assert client.post("/api/clips/a/trim", json={"start": 0, "end": 99}).status_code == 400
    assert client.post("/api/clips/a/trim", json={}).status_code == 400
    assert client.post("/api/clips/zzz/trim", json={"start": 0, "end": 5}).status_code == 404


def test_trim_cuts_the_clip_and_returns_updated_metadata(client):
    import subprocess

    from conftest import FFMPEG_PATH

    if FFMPEG_PATH is None:
        pytest.skip("ffmpeg를 찾을 수 없다")
    clips = client.app.state.clips_dir_for_test
    _write_clip(clips, "a", durationSec=10.0, videoOffsetSec=50.0)
    subprocess.run(
        [str(FFMPEG_PATH), "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
         "testsrc=size=320x180:rate=30:duration=10", "-c:v", "libx264", "-g", "30", "-pix_fmt", "yuv420p",
         str(clips / "a.mp4")],
        check=True,
    )

    resp = client.post("/api/clips/a/trim", json={"start": 2, "end": 8})

    assert resp.status_code == 200
    body = resp.json()
    assert body["durationSec"] == 6.0 and body["videoOffsetSec"] == 52.0 and body["trimmed"] is True
    assert body["id"] == "a" and body["sizeBytes"] == (clips / "a.mp4").stat().st_size


def test_deleting_many_clips_at_once_all_succeed(client):
    import threading

    clips = client.app.state.clips_dir_for_test
    client.put("/api/config", json={"ui": {"deleteMode": "permanent"}})
    ids = [f"c{i}" for i in range(8)]
    for clip_id in ids:
        _write_clip(clips, clip_id)
    statuses = []

    def delete(clip_id):
        statuses.append(client.delete(f"/api/clips/{clip_id}").status_code)

    threads = [threading.Thread(target=delete, args=(clip_id,)) for clip_id in ids]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert statuses == [200] * 8
    assert client.get("/api/clips").json() == []


def test_confirm_delete_option_defaults_to_true_and_can_be_turned_off(client):
    assert client.get("/api/config").json()["ui"]["confirmDelete"] is True

    client.put("/api/config", json={"ui": {"confirmDelete": False}})

    assert client.get("/api/config").json()["ui"]["confirmDelete"] is False


def test_delete_mode_option_defaults_to_recycle_and_can_be_changed(client):
    assert client.get("/api/config").json()["ui"]["deleteMode"] == "recycle"

    client.put("/api/config", json={"ui": {"deleteMode": "permanent"}})

    assert client.get("/api/config").json()["ui"]["deleteMode"] == "permanent"


def _wait_for_job(client, key, *, tries=100):
    import time

    for _ in range(tries):
        body = client.get(f"/api/games/reprocess/{key}").json()
        if body["state"] not in ("running", "queued"):
            return body
        time.sleep(0.02)
    raise AssertionError("작업이 끝나지 않았다")


@pytest.fixture
def reprocess_env(client, monkeypatch, tmp_path):
    from lumia_briefing_room.api import app as app_module

    root = tmp_path / "recordings"
    root.mkdir()
    client.put("/api/config", json={"paths": {"steamRecording": str(root)}})
    monkeypatch.setattr(app_module, "discover_ffmpeg", lambda: Path("ffmpeg"))
    monkeypatch.setattr(app_module, "read_boundaries", lambda cfg: [])
    _write_clip(client.app.state.clips_dir_for_test, "a", sessionDir="bg_1_20260921_105357",
                matchStartUtc="2026-09-21T10:58:21Z")
    return app_module


def test_reprocess_runs_in_the_background_and_reports_the_new_clip_count(client, reprocess_env, monkeypatch):
    seen = {}

    def fake(**kw):
        seen.update(kw)
        return [Path("x.json"), Path("y.json")]

    monkeypatch.setattr(reprocess_env, "reprocess_game", fake)

    resp = client.post("/api/games/reprocess", json={"clipId": "a"})

    assert resp.status_code == 202
    status = _wait_for_job(client, resp.json()["key"])
    assert status == {"state": "done", "message": "", "clips": 2, "position": None}
    assert seen["ref"].session_name == "bg_1_20260921_105357"
    assert seen["ref"].match_start == "2026-09-21T10:58:21Z"


def test_reprocess_shows_the_reason_when_the_original_recording_is_gone(client, reprocess_env, monkeypatch):
    from lumia_briefing_room.pipeline.reprocess import ReprocessError

    def fake(**kw):
        raise ReprocessError("원본 녹화가 이미 삭제되어 다시 분석할 수 없습니다")

    monkeypatch.setattr(reprocess_env, "reprocess_game", fake)

    key = client.post("/api/games/reprocess", json={"clipId": "a"}).json()["key"]

    assert _wait_for_job(client, key) == {
        "state": "error", "message": "원본 녹화가 이미 삭제되어 다시 분석할 수 없습니다", "clips": 0, "position": None,
    }


def test_reprocess_queues_other_games_behind_the_running_one_instead_of_rejecting(client, reprocess_env, monkeypatch):
    import threading

    _write_clip(client.app.state.clips_dir_for_test, "b", sessionDir="bg_1_20260921_120000", matchStartUtc="2026-09-21T12:10:00Z")
    release = threading.Event()
    order = []

    def fake(**kw):
        order.append(kw["ref"].session_name)
        release.wait(5)
        return []

    monkeypatch.setattr(reprocess_env, "reprocess_game", fake)
    first = client.post("/api/games/reprocess", json={"clipId": "a"})
    second = client.post("/api/games/reprocess", json={"clipId": "b"})

    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["position"] == 0 and second.json()["position"] == 1
    waiting = client.get(f"/api/games/reprocess/{second.json()['key']}").json()
    assert waiting["state"] == "queued" and waiting["position"] == 1
    assert client.post("/api/games/reprocess", json={"clipId": "b"}).json()["position"] == 1, "같은 게임을 또 눌러도 한 번만 줄 선다"
    release.set()
    _wait_for_job(client, first.json()["key"])
    assert _wait_for_job(client, second.json()["key"])["state"] == "done"
    assert order == ["bg_1_20260921_105357", "bg_1_20260921_120000"]


def test_reprocess_rejects_unknown_clip_and_missing_setup(client, reprocess_env, monkeypatch):
    assert client.post("/api/games/reprocess", json={"clipId": "zzz"}).status_code == 404
    assert client.post("/api/games/reprocess", json={}).status_code == 400

    monkeypatch.setattr(reprocess_env, "discover_ffmpeg", lambda: None)
    assert client.post("/api/games/reprocess", json={"clipId": "a"}).status_code == 503


def test_reprocess_registers_an_activity_task_while_running(client, reprocess_env, monkeypatch):
    """plan-ui.md §0 "다시 분석 중 진행 표시를 영상 파일 탭 수준으로 통일" — 헤더 공통 배너(activity.py)에도 뜬다."""
    import threading
    import time

    from lumia_briefing_room.activity import registry

    release = threading.Event()
    seen: dict = {}

    def fake(**kw):
        seen["tasks"] = registry.snapshot()
        release.wait(5)
        return []

    monkeypatch.setattr(reprocess_env, "reprocess_game", fake)

    resp = client.post("/api/games/reprocess", json={"clipId": "a"})
    assert resp.status_code == 202

    deadline = time.time() + 3
    while "tasks" not in seen and time.time() < deadline:
        time.sleep(0.02)

    assert seen.get("tasks") and seen["tasks"][0]["kind"] == "reprocess"
    assert "다시 분석" in seen["tasks"][0]["label"]

    release.set()
    _wait_for_job(client, resp.json()["key"])
    assert registry.snapshot() == []


def test_deleting_a_labeled_clip_keeps_its_label_and_evidence(client):
    clips = client.app.state.clips_dir_for_test
    _write_clip(clips, "a", userLabel="pvp", pvpSignals=["kill_delta"])
    _write_clip(clips, "b")

    client.delete("/api/clips/a")
    client.delete("/api/clips/b")

    kept = json.loads((clips / ".labels" / "a.json").read_text(encoding="utf-8"))
    assert kept["userLabel"] == "pvp" and kept["pvpSignals"] == ["kill_delta"]
    assert not (clips / ".labels" / "b.json").exists()


def test_split_rejects_bad_ranges_and_unknown_clip(client):
    _write_clip(client.app.state.clips_dir_for_test, "a", durationSec=20.0)

    assert client.post("/api/clips/a/split", json={"ranges": [{"start": 0, "end": 6}, {"start": 5, "end": 9}]}).status_code == 400
    assert client.post("/api/clips/a/split", json={"ranges": []}).status_code == 400
    assert client.post("/api/clips/a/split", json={}).status_code == 400
    assert client.post("/api/clips/zzz/split", json={"ranges": [{"start": 0, "end": 5}, {"start": 6, "end": 9}]}).status_code == 404


def test_split_creates_new_clips_and_deletes_the_original(client):
    import subprocess

    from conftest import FFMPEG_PATH

    if FFMPEG_PATH is None:
        pytest.skip("ffmpeg를 찾을 수 없다")
    clips = client.app.state.clips_dir_for_test
    _write_clip(clips, "a", durationSec=10.0, videoOffsetSec=50.0)
    subprocess.run(
        [str(FFMPEG_PATH), "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
         "testsrc=size=320x180:rate=30:duration=10", "-c:v", "libx264", "-g", "30", "-pix_fmt", "yuv420p",
         str(clips / "a.mp4")],
        check=True,
    )

    resp = client.post("/api/clips/a/split", json={"ranges": [{"start": 1, "end": 4}, {"start": 6, "end": 9}]})

    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert ids == ["a-p1", "a-p2"]
    listed = {c["id"] for c in client.get("/api/clips").json()}
    assert listed == {"a-p1", "a-p2"}
    assert not (clips / "a.json").exists()


def test_patch_label_note_is_saved_trimmed_and_capped(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", userLabel="pvp")

    assert client.patch("/api/clips/a", json={"labelNote": "  적 둘과 교전  "}).json()["labelNote"] == "적 둘과 교전"
    long = client.patch("/api/clips/a", json={"labelNote": "가" * 900}).json()["labelNote"]
    assert len(long) == 500
    assert json.loads((clips_dir / "a.json").read_text(encoding="utf-8"))["labelNote"] == long


def test_patch_label_note_rejects_non_string(client):
    _write_clip(client.app.state.clips_dir_for_test, "a")

    assert client.patch("/api/clips/a", json={"labelNote": 5}).status_code == 400


def test_clearing_the_label_clears_its_note(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", userLabel="pvp", labelNote="메모")

    data = client.patch("/api/clips/a", json={"userLabel": None}).json()

    assert data["userLabel"] is None and data["labelNote"] is None


def test_label_note_is_kept_in_the_label_archive(client):
    clips = client.app.state.clips_dir_for_test
    _write_clip(clips, "a", userLabel="pve", labelNote="대치만 함")

    client.delete("/api/clips/a")

    kept = json.loads((clips / ".labels" / "a.json").read_text(encoding="utf-8"))
    assert kept["labelNote"] == "대치만 함"


def test_labeling_records_when_the_label_was_set_and_clearing_removes_it(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a")
    first = client.patch("/api/clips/a", json={"userLabel": "pvp"}).json()
    assert first["labeledAt"].endswith("Z") and len(first["labeledAt"]) == 20
    cleared = client.patch("/api/clips/a", json={"userLabel": None}).json()
    assert cleared["labeledAt"] is None


def test_setting_the_same_label_again_or_editing_the_note_keeps_the_original_time(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", userLabel="pvp", labeledAt="2026-09-20T01:02:03Z")
    same = client.patch("/api/clips/a", json={"userLabel": "pvp"}).json()
    assert same["labeledAt"] == "2026-09-20T01:02:03Z"
    noted = client.patch("/api/clips/a", json={"labelNote": "메모"}).json()
    assert noted["labeledAt"] == "2026-09-20T01:02:03Z"


def test_changing_the_label_value_updates_the_time(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", userLabel="pvp", labeledAt="2026-09-20T01:02:03Z")
    changed = client.patch("/api/clips/a", json={"userLabel": "pve"}).json()
    assert changed["labeledAt"] != "2026-09-20T01:02:03Z"


def test_a_label_without_a_recorded_time_gets_one_when_touched(client):
    clips_dir = client.app.state.clips_dir_for_test
    _write_clip(clips_dir, "a", userLabel="pvp")
    assert client.patch("/api/clips/a", json={"userLabel": "pvp"}).json()["labeledAt"]


def test_legacy_trash_status_counts_leftover_clips_across_both_roots(tmp_path):
    from lumia_briefing_room.config import PathsConfig

    clips, vod = tmp_path / "clips", tmp_path / "vod"
    cfg = Config(paths=PathsConfig(clips=clips, vod_clips=vod, temp=tmp_path / "tmp"))
    app = create_app(cfg, config_path=tmp_path / "config.json")
    test_client = TestClient(app)
    _write_clip(clips / ".trash", "a")
    _write_clip(vod / ".trash", "b")

    assert test_client.get("/api/legacy-trash").json() == {"count": 2}


def test_legacy_trash_status_is_zero_when_nothing_is_left(client):
    assert client.get("/api/legacy-trash").json() == {"count": 0}


def test_legacy_trash_migrate_restore_moves_clips_back_to_the_list(client):
    clips_dir = client.app.state.clips_dir_for_test
    old_dir = client.app.state.video_dir_for_test
    _write_clip(old_dir / ".trash", "a")

    resp = client.post("/api/legacy-trash/migrate", json={"action": "restore"})

    assert resp.json() == {"migrated": 1}
    assert (clips_dir / "a.json").exists(), "복원한 정보 파일은 앱 데이터 library 로 옮겨진다"
    assert (old_dir / "a.mp4").exists()
    assert client.get("/api/legacy-trash").json() == {"count": 0}


def test_legacy_trash_migrate_recycle_sends_clips_to_the_recycle_bin(client, monkeypatch):
    from lumia_briefing_room.pipeline import delete_helper

    _write_clip(client.app.state.video_dir_for_test / ".trash", "a")
    sent = []
    monkeypatch.setattr(delete_helper, "_send2trash", lambda path: sent.append(Path(path).name))

    resp = client.post("/api/legacy-trash/migrate", json={"action": "recycle"})

    assert resp.json() == {"migrated": 1}
    assert set(sent) == {"a.json", "a.mp4", "a.jpg"}


def test_legacy_trash_migrate_rejects_unknown_action(client):
    assert client.post("/api/legacy-trash/migrate", json={"action": "nope"}).status_code == 400
