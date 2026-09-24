import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig
from lumia_briefing_room.pipeline.move_clips import MoveError, move_clips_dir


def _write_clip(root: Path, clip_id: str, *, stored_thumb: str | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{clip_id}.mp4").write_bytes(b"video")
    (root / ".thumbs").mkdir(exist_ok=True)
    (root / ".thumbs" / f"{clip_id}.jpg").write_bytes(b"\xff\xd8thumb")
    meta = {
        "title": clip_id, "tags": [], "pinned": False, "deletedAt": None,
        "thumbnailPath": stored_thumb or f".thumbs/{clip_id}.jpg",
    }
    (root / f"{clip_id}.json").write_text(json.dumps(meta), encoding="utf-8")


def test_moves_clips_thumbnails_and_side_folders(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    _write_clip(old, "a")
    _write_clip(old / ".trash", "t")
    (old / ".proxy").mkdir()
    (old / ".proxy" / "a.mp4").write_bytes(b"proxy")
    (old / ".games").mkdir()
    (old / ".games" / "g.json").write_text("{}", encoding="utf-8")

    moved = move_clips_dir(old, new)

    assert moved == 1
    assert (new / "a.json").exists() and (new / "a.mp4").exists()
    assert (new / ".thumbs" / "a.jpg").exists()
    assert (new / ".trash" / "t.json").exists() and (new / ".trash" / ".thumbs" / "t.jpg").exists()
    assert (new / ".proxy" / "a.mp4").exists()
    assert (new / ".games" / "g.json").exists()
    assert not (old / "a.json").exists()
    assert not (old / ".thumbs").exists()


def test_leaves_unrelated_files_alone(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    _write_clip(old, "a")
    (old / "notes.txt").write_text("mine", encoding="utf-8")
    (old / "vacation.mp4").write_bytes(b"not a clip")

    move_clips_dir(old, new)

    assert (old / "notes.txt").exists()
    assert (old / "vacation.mp4").exists()
    assert not (new / "vacation.mp4").exists()


def test_refuses_when_target_already_has_same_file(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    _write_clip(old, "a")
    _write_clip(new, "a")

    with pytest.raises(MoveError):
        move_clips_dir(old, new)

    assert (old / "a.json").exists()


def test_refuses_nested_folders(tmp_path):
    old = tmp_path / "old"
    _write_clip(old, "a")

    with pytest.raises(MoveError):
        move_clips_dir(old, old / "inner")
    with pytest.raises(MoveError):
        move_clips_dir(old / "inner", old)


def test_same_folder_or_missing_old_folder_moves_nothing(tmp_path):
    old = tmp_path / "old"
    _write_clip(old, "a")

    assert move_clips_dir(old, old) == 0
    assert move_clips_dir(tmp_path / "missing", tmp_path / "new") == 0


@pytest.fixture
def client(tmp_path):
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp"))
    return TestClient(create_app(cfg, config_path=tmp_path / "config.json"))


def _start_move(client, source, path):
    resp = client.post("/api/clips-dir/move", json={"source": source, "path": str(path)})
    if resp.status_code != 202:
        return resp, None
    deadline = time.time() + 10
    while time.time() < deadline:
        status = client.get("/api/clips-dir/move").json()
        if status["state"] != "running":
            return resp, status
        time.sleep(0.02)
    raise AssertionError("이동이 끝나지 않았다")


def test_progress_reports_bytes_up_to_total(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    _write_clip(old, "a")
    _write_clip(old, "b")
    seen = []

    move_clips_dir(old, new, progress=lambda done, total: seen.append((done, total)))

    total = seen[0][1]
    assert total > 0
    assert seen[0][0] == 0 and seen[-1] == (total, total)
    assert [d for d, _ in seen] == sorted(d for d, _ in seen)


def test_api_moves_clips_and_updates_config(client, tmp_path):
    _write_clip(tmp_path / "clips", "a", stored_thumb=str(tmp_path / "clips" / ".thumbs" / "a.jpg"))
    new = tmp_path / "elsewhere"

    resp, status = _start_move(client, "steam", new)

    assert resp.status_code == 202
    assert status["state"] == "done" and status["moved"] == 1
    assert status["doneBytes"] == status["totalBytes"] > 0
    assert client.get("/api/config").json()["paths"]["clips"] == str(new)
    assert [c["id"] for c in client.get("/api/clips").json()] == ["a"]
    assert client.get("/api/clips/a/thumbnail").status_code == 200


def test_api_conflict_keeps_old_config(client, tmp_path):
    _write_clip(tmp_path / "clips", "a")
    _write_clip(tmp_path / "elsewhere", "a")

    resp, _ = _start_move(client, "steam", tmp_path / "elsewhere")

    assert resp.status_code == 409
    assert client.get("/api/config").json()["paths"]["clips"] == str(tmp_path / "clips")


def test_api_moves_vod_clips(client, tmp_path):
    vod = tmp_path / "vodclips"
    client.put("/api/config", json={"paths": {"vodClips": str(vod)}})
    _write_clip(vod, "vod_a")

    _, status = _start_move(client, "vod", tmp_path / "vod2")

    assert status["state"] == "done"
    assert client.get("/api/config").json()["paths"]["vodClips"] == str(tmp_path / "vod2")
    assert (tmp_path / "vod2" / "vod_a.json").exists()


def test_api_nothing_to_move_still_switches_folder(client, tmp_path):
    _, status = _start_move(client, "steam", tmp_path / "fresh")

    assert status["state"] == "done" and status["moved"] == 0
    assert client.get("/api/config").json()["paths"]["clips"] == str(tmp_path / "fresh")
