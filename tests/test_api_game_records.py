import json

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig, RetentionConfig
from lumia_briefing_room.pipeline.game_records import load_records, records_dir_for

RESULT = {"matchType": "rank", "matchLabel": "랭크", "placement": 2, "total": 8, "outcome": None, "nickname": "me", "character": "아야"}


def write_clip(root, clip_id, *, start="2026-09-01T10:00:00Z"):
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{clip_id}.mp4").write_bytes(b"x" * 10)
    image = root / ".thumbs" / f"{start[:10]}_result.jpg"
    image.parent.mkdir(exist_ok=True)
    image.write_bytes(b"result-jpg")
    meta = {
        "title": clip_id, "tags": ["kill"], "pinned": False, "deletedAt": None, "thumbnailPath": None,
        "sessionDir": "s1", "matchStartUtc": start, "matchResult": {**RESULT, "imagePath": str(image)},
    }
    (root / f"{clip_id}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def make_client(tmp_path, *, keep=True):
    clips = tmp_path / "clips"
    cfg = Config(paths=PathsConfig(clips=clips, temp=tmp_path / "tmp"), retention=RetentionConfig(keep_game_records=keep))
    return TestClient(create_app(cfg, config_path=tmp_path / "config.json")), clips


def test_permanent_delete_of_last_clip_leaves_a_record_row(tmp_path):
    client, clips = make_client(tmp_path)
    write_clip(clips, "a_01")
    client.post("/api/clips/a_01/trash")
    client.delete("/api/clips/a_01")

    rows = client.get("/api/games/records").json()

    assert len(rows) == 1
    assert rows[0]["sessionDir"] == "s1" and rows[0]["matchResult"]["placement"] == 2
    assert client.get(f"/api/games/records/{rows[0]['id']}/result-image").content == b"result-jpg"


def test_record_is_hidden_while_the_game_still_has_live_clips(tmp_path):
    client, clips = make_client(tmp_path)
    write_clip(clips, "a_01")
    write_clip(clips, "a_02")
    client.post("/api/clips/a_01/trash")
    client.delete("/api/clips/a_01")

    assert client.get("/api/games/records").json() == []


def test_empty_trash_records_games(tmp_path):
    client, clips = make_client(tmp_path)
    write_clip(clips, "a_01")
    client.post("/api/clips/a_01/trash")
    client.post("/api/trash/empty")

    assert len(client.get("/api/games/records").json()) == 1


def test_keep_game_records_off_leaves_nothing(tmp_path):
    client, clips = make_client(tmp_path, keep=False)
    write_clip(clips, "a_01")
    client.post("/api/clips/a_01/trash")
    client.delete("/api/clips/a_01")

    assert client.get("/api/games/records").json() == []
    assert load_records(records_dir_for(clips)) == []


def test_delete_record_removes_summary_and_image(tmp_path):
    client, clips = make_client(tmp_path)
    write_clip(clips, "a_01")
    client.post("/api/clips/a_01/trash")
    client.delete("/api/clips/a_01")
    rid = client.get("/api/games/records").json()[0]["id"]

    assert client.delete(f"/api/games/records/{rid}").status_code == 200
    assert client.get("/api/games/records").json() == []
    assert client.get(f"/api/games/records/{rid}/result-image").status_code == 404
    assert client.delete(f"/api/games/records/{rid}").status_code == 404


@pytest.mark.parametrize("rid", ["..", "a/b", "..%2Fx"])
def test_record_routes_reject_path_tricks(tmp_path, rid):
    client, _ = make_client(tmp_path)
    assert client.get(f"/api/games/records/{rid}/result-image").status_code in (404, 400)
