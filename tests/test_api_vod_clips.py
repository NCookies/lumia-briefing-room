import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig


def write_clip(root: Path, clip_id: str, **meta):
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{clip_id}.mp4").write_bytes(b"fake video bytes 0123456789")
    thumbs = root / ".thumbs"
    thumbs.mkdir(exist_ok=True)
    thumb = thumbs / f"{clip_id}.jpg"
    thumb.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
    data = {
        "title": clip_id, "tags": ["kill"], "dayNight": "day", "pinned": False,
        "deletedAt": None, "thumbnailPath": str(thumb), **meta,
    }
    (root / f"{clip_id}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def env(tmp_path):
    steam, vod = tmp_path / "clips", tmp_path / "vod"
    cfg = Config(paths=PathsConfig(clips=steam, vod_clips=vod, temp=tmp_path / "tmp"))
    app = create_app(cfg, config_path=tmp_path / "config.json")
    write_clip(steam, "steam_a")
    write_clip(vod, "vod_x_g01_000010", source="vod", vodId="x", vodGameIndex=1)
    write_clip(vod, "vod_x_g01_000090", source="vod", vodId="x", vodGameIndex=1, tags=["death"])
    return TestClient(app), steam, vod


def ids(resp):
    return {c["id"] for c in resp.json()}


def test_default_list_is_steam_only_and_source_vod_is_vod_only(env):
    client, _, _ = env

    assert ids(client.get("/api/clips")) == {"steam_a"}
    assert ids(client.get("/api/clips", params={"source": "vod"})) == {
        "vod_x_g01_000010", "vod_x_g01_000090",
    }


def test_vod_list_supports_the_same_filters(env):
    client, _, _ = env

    resp = client.get("/api/clips", params={"source": "vod", "tags": "death"})

    assert ids(resp) == {"vod_x_g01_000090"}


def test_unknown_source_is_rejected(env):
    client, _, _ = env

    assert client.get("/api/clips", params={"source": "nope"}).status_code == 400


def test_clip_routes_find_vod_clips_by_id(env):
    client, _, _ = env
    cid = "vod_x_g01_000010"

    assert client.get(f"/api/clips/{cid}").json()["source"] == "vod"
    assert client.get(f"/api/clips/{cid}/video").status_code == 200
    assert client.get(f"/api/clips/{cid}/thumbnail").status_code == 200
    patched = client.patch(f"/api/clips/{cid}", json={"userLabel": "pvp", "title": "새 제목"})
    assert patched.status_code == 200 and patched.json()["userLabel"] == "pvp"
    assert client.get(f"/api/clips/{cid}").json()["title"] == "새 제목"


def test_delete_stays_inside_the_vod_folder_and_only_touches_that_clip(env):
    client, steam, vod = env
    cid = "vod_x_g01_000010"
    client.put("/api/config", json={"ui": {"deleteMode": "permanent"}})

    assert client.delete(f"/api/clips/{cid}").status_code == 200
    assert not (vod / f"{cid}.mp4").exists()
    assert (steam / "steam_a.json").exists()
    assert ids(client.get("/api/clips", params={"source": "vod"})) == {"vod_x_g01_000090"}


def test_missing_clip_is_404(env):
    client, _, _ = env

    assert client.get("/api/clips/vod_nope").status_code == 404
    assert client.delete("/api/clips/vod_nope").status_code == 404
