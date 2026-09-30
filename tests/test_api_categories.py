import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api import game_routes
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig, resolve_paths
from lumia_briefing_room.pipeline import clip_from_full as cff

KEY = "20260930_002400"


def _cand(cid, start, end):
    return {"id": cid, "start": start, "end": end, "combatStart": start + 5, "combatEnd": end - 5, "title": cid,
            "tags": ["kill"], "certain": True, "user": {}}


def make_client(tmp_path, monkeypatch, paths: PathsConfig):
    cfg = Config(paths=paths)
    app = create_app(cfg, config_path=tmp_path / "config.json")
    resolved = resolve_paths(cfg.paths)
    folder = resolved.games_steam / KEY
    folder.mkdir(parents=True)
    (folder / "full.mp4").write_bytes(b"0123456789" * 100)
    game = {
        "gameKey": KEY, "matchStartUtc": "2026-09-30T00:24:00Z", "matchEndUtc": "2026-09-30T00:46:00Z",
        "sessionDir": "bg_1", "sessionStartUtc": "2026-09-30T00:00:00Z", "gameMode": "battle_royale",
        "sourceWidth": 2560, "sourceHeight": 1440, "matchResult": {"placement": 1}, "portraits": {}, "pinned": False,
        "fullVideo": {"path": "full.mp4", "sizeBytes": 1000, "durationSec": 600.0, "offsetSec": 300.0,
                      "segmentDurationSec": 3.0, "sourceIncomplete": False, "audioStatus": "full"},
        "candidates": [_cand(f"{KEY}_01", 100, 140), _cand(f"{KEY}_02", 300, 330), _cand(f"{KEY}_03", 400, 430)],
        "userCandidates": [], "markers": [],
    }
    (folder / "game.json").write_text(json.dumps(game), encoding="utf-8")
    monkeypatch.setattr(cff, "_run_ffmpeg", lambda cmd: Path(cmd[-1]).write_bytes(b"clip"))
    monkeypatch.setattr(cff, "make_thumbnail", lambda clip, out, **kw: out.parent.mkdir(parents=True, exist_ok=True) or out.write_bytes(b"t"))
    monkeypatch.setattr(game_routes, "discover_ffmpeg", lambda: Path("ffmpeg"))
    client = TestClient(app)
    client.resolved = resolved
    return client


@pytest.fixture
def client(tmp_path, monkeypatch):
    return make_client(tmp_path, monkeypatch, PathsConfig(root=tmp_path / "store", temp=tmp_path / "tmp"))


def names(client):
    return [c["name"] for c in client.get("/api/categories").json()["categories"]]


def videos(client, folder):
    base = client.resolved.clips_root / folder
    return sorted(p.name for p in base.glob("*.mp4")) if base.is_dir() else []


def save(client, cid, **body):
    return client.post(f"/api/games/{KEY}/candidates/{KEY}_{cid}/save", json=body)


def test_default_categories_are_always_listed_with_auto_last(client):
    body = client.get("/api/categories").json()
    assert body["enabled"] is True
    assert [(c["name"], c["auto"], c["default"], c["clipCount"]) for c in body["categories"]] == [
        ("보관함", False, True, 0), ("자동 보관", True, False, 0)]


def test_created_categories_sit_between_the_default_and_auto(client):
    assert client.post("/api/categories", json={"name": "아야"}).status_code == 201
    assert client.post("/api/categories", json={"name": "가나다"}).status_code == 201
    assert names(client) == ["보관함", "가나다", "아야", "자동 보관"]
    assert (client.resolved.clips_root / "아야").is_dir()


def test_category_names_are_validated(client):
    assert client.post("/api/categories", json={"name": "아야"}).status_code == 201
    assert client.post("/api/categories", json={"name": "아야"}).status_code == 409
    assert client.post("/api/categories", json={"name": "보관함"}).status_code == 409
    for bad in ("", "  ", ".숨김", "a/b", "a\\b", "..", "con?"):
        assert client.post("/api/categories", json={"name": bad}).status_code == 400, bad


def test_saving_without_a_category_goes_to_the_default_folder(client):
    resp = save(client, "01")
    assert resp.status_code == 200 and resp.json()["category"] == "보관함"
    assert videos(client, "보관함") == [f"{KEY}_01.mp4"]


def test_saving_into_a_category_creates_it_when_missing(client):
    assert save(client, "01", category="아야").json()["category"] == "아야"
    assert videos(client, "아야") == [f"{KEY}_01.mp4"]
    assert "아야" in names(client)
    assert save(client, "02", category="../밖").status_code == 400
    assert save(client, "02", category="자동 보관").status_code == 200


def test_category_list_counts_clips_and_names_a_thumbnail_clip(client):
    save(client, "01", category="아야")
    save(client, "02", category="아야")
    listed = {c["name"]: c for c in client.get("/api/categories").json()["categories"]}
    assert listed["아야"]["clipCount"] == 2
    assert listed["아야"]["thumbnailClipId"] in (f"{KEY}_01", f"{KEY}_02")
    assert listed["보관함"]["clipCount"] == 0 and listed["보관함"]["thumbnailClipId"] is None


def test_game_detail_reports_the_category_of_each_saved_clip(client):
    save(client, "01", category="아야")
    save(client, "02")
    cands = {c["id"]: c for c in client.get(f"/api/games/{KEY}").json()["candidates"]}
    assert cands[f"{KEY}_01"]["user"]["savedCategory"] == "아야"
    assert cands[f"{KEY}_02"]["user"]["savedCategory"] == "보관함"
    assert "savedCategory" not in cands[f"{KEY}_03"]["user"]


def test_batch_save_takes_a_category(client):
    body = client.post(f"/api/games/{KEY}/save", json={"mode": "all", "category": "아야"}).json()
    assert len(body["saved"]) == 3 and videos(client, "아야") == [f"{KEY}_0{i}.mp4" for i in (1, 2, 3)]


def test_resaving_keeps_the_clip_in_its_category(client):
    save(client, "01", category="아야")
    client.patch(f"/api/games/{KEY}/candidates/{KEY}_01", json={"start": 90, "end": 150})
    save(client, "01")
    assert videos(client, "아야") == [f"{KEY}_01.mp4"] and videos(client, "보관함") == []


def test_moving_clips_between_categories(client):
    save(client, "01")
    save(client, "02")
    client.post("/api/categories", json={"name": "아야"})
    resp = client.post("/api/categories/move", json={"clipIds": [f"{KEY}_01", f"{KEY}_02"], "category": "아야"})
    assert resp.status_code == 200 and resp.json()["moved"] == 2
    assert videos(client, "아야") == [f"{KEY}_01.mp4", f"{KEY}_02.mp4"] and videos(client, "보관함") == []
    cand = client.get(f"/api/games/{KEY}").json()["candidates"][0]
    assert cand["user"]["savedCategory"] == "아야"
    assert client.get(f"/api/clips/{KEY}_01").status_code == 200


def test_moving_to_the_same_category_is_a_noop_and_unknown_inputs_are_rejected(client):
    save(client, "01")
    assert client.post("/api/categories/move", json={"clipIds": [f"{KEY}_01"], "category": "보관함"}).json()["moved"] == 0
    assert client.post("/api/categories/move", json={"clipIds": ["nope"], "category": "보관함"}).status_code == 404
    assert client.post("/api/categories/move", json={"clipIds": [], "category": "보관함"}).status_code == 400
    assert client.post("/api/categories/move", json={"clipIds": [f"{KEY}_01"], "category": "x/y"}).status_code == 400


def test_moving_into_a_folder_with_the_same_file_name_keeps_both(client):
    save(client, "01")
    other = client.resolved.clips_root / "아야"
    other.mkdir()
    (other / f"{KEY}_01.mp4").write_bytes(b"other")
    client.post("/api/categories/move", json={"clipIds": [f"{KEY}_01"], "category": "아야"})
    assert (other / f"{KEY}_01.mp4").read_bytes() == b"other"
    assert len(videos(client, "아야")) == 2


def test_legacy_layout_has_no_categories_and_saves_where_it_always_did(tmp_path, monkeypatch):
    paths = PathsConfig(clips=tmp_path / "clips", vod_clips=tmp_path / "vod", games=tmp_path / "games", temp=tmp_path / "tmp")
    client = make_client(tmp_path, monkeypatch, paths)
    assert client.get("/api/categories").json() == {"enabled": False, "categories": []}
    assert client.post("/api/categories", json={"name": "아야"}).status_code == 409
    resp = save(client, "01", category="아야")
    assert resp.status_code == 200 and resp.json()["category"] is None
    assert (tmp_path / "clips" / f"{KEY}_01.mp4").exists()


def _user(client, cid):
    cands = {c["id"]: c for c in client.get(f"/api/games/{KEY}").json()["candidates"]}
    return cands[f"{KEY}_{cid}"]["user"]


def test_a_clip_in_the_auto_folder_is_not_archived_but_one_in_any_other_category_is(client):
    save(client, "01")
    save(client, "02", category="아야")
    save(client, "03", category="자동 보관")
    assert _user(client, "01")["archived"] is True
    assert _user(client, "02")["archived"] is True
    user = _user(client, "03")
    assert user["archived"] is False and user["savedCategory"] == "자동 보관", "클립은 있지만 어디에도 속하지 않은 것으로 본다"


def test_moving_an_auto_clip_into_a_category_archives_it_and_moving_back_unarchives_it(client):
    save(client, "01", category="자동 보관")
    client.post("/api/categories/move", json={"clipIds": [f"{KEY}_01"], "category": "보관함"})
    assert _user(client, "01")["archived"] is True
    client.post("/api/categories/move", json={"clipIds": [f"{KEY}_01"], "category": "자동 보관"})
    assert _user(client, "01")["archived"] is False


def test_unsaved_candidates_have_no_archive_flag(client):
    assert "archived" not in _user(client, "01")


def test_legacy_layout_saved_clips_count_as_archived(tmp_path, monkeypatch):
    paths = PathsConfig(clips=tmp_path / "clips", vod_clips=tmp_path / "vod", games=tmp_path / "games", temp=tmp_path / "tmp")
    client = make_client(tmp_path, monkeypatch, paths)
    save(client, "01")
    assert _user(client, "01")["archived"] is True
