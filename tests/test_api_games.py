import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api import game_routes
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig
from lumia_briefing_room.pipeline import clip_from_full as cff

KEY = "20260930_002400"


def _cand(cid, start, end, certain=False, user=None):
    return {"id": cid, "start": start, "end": end, "combatStart": start + 5, "combatEnd": end - 5, "title": cid,
            "tags": ["kill"] if certain else ["no_result"], "certain": certain, "user": user or {}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp", games=tmp_path / "games"))
    app = create_app(cfg, config_path=tmp_path / "config.json")
    folder = tmp_path / "games" / KEY
    folder.mkdir(parents=True)
    (folder / "full.mp4").write_bytes(b"0123456789" * 100)
    (folder / "result.jpg").write_bytes(b"jpg")
    game = {
        "gameKey": KEY, "matchStartUtc": "2026-09-30T00:24:00Z", "matchEndUtc": "2026-09-30T00:46:00Z",
        "sessionDir": "bg_1", "sessionStartUtc": "2026-09-30T00:00:00Z", "gameMode": "battle_royale",
        "sourceWidth": 2560, "sourceHeight": 1440, "matchResult": {"placement": 1, "imagePath": "result.jpg"},
        "portraits": {}, "pinned": False,
        "fullVideo": {"path": "full.mp4", "sizeBytes": 1000, "durationSec": 600.0, "offsetSec": 300.0,
                      "segmentDurationSec": 3.0, "sourceIncomplete": False, "audioStatus": "full"},
        "candidates": [_cand(f"{KEY}_01", 100, 140, certain=True), _cand(f"{KEY}_02", 300, 330)],
        "userCandidates": [], "markers": [],
    }
    (folder / "game.json").write_text(json.dumps(game), encoding="utf-8")

    cuts = []
    monkeypatch.setattr(cff, "_run_ffmpeg", lambda cmd: (cuts.append(cmd), Path(cmd[-1]).write_bytes(b"clip")))
    monkeypatch.setattr(cff, "make_thumbnail", lambda clip, out, **kw: out.parent.mkdir(parents=True, exist_ok=True) or out.write_bytes(b"t"))
    monkeypatch.setattr(game_routes, "discover_ffmpeg", lambda: Path("ffmpeg"))
    c = TestClient(app)
    c.cuts = cuts
    c.tmp = tmp_path
    return c


def test_list_shows_counts_and_flags(client):
    (game,) = client.get("/api/games").json()["games"]
    assert game["key"] == KEY and game["hasFullVideo"] is True
    assert game["candidateCount"] == 2 and game["certainCount"] == 1 and game["savedClipCount"] == 0
    assert game["matchResult"]["placement"] == 1


def test_detail_and_unknown_game(client):
    assert client.get(f"/api/games/{KEY}").json()["candidates"][0]["id"] == f"{KEY}_01"
    assert client.get("/api/games/20990101_000000").status_code == 404
    assert client.get("/api/games/records").status_code != 404  # 기존 경로가 가려지지 않는다


def test_video_supports_range_requests(client):
    resp = client.get(f"/api/games/{KEY}/video", headers={"Range": "bytes=10-19"})
    assert resp.status_code == 206
    assert resp.content == b"0123456789"


def test_video_of_a_game_whose_video_was_cleaned_up_is_404(client):
    (client.tmp / "games" / KEY / "full.mp4").unlink()
    assert client.get(f"/api/games/{KEY}/video").status_code == 404
    assert client.get("/api/games").json()["games"][0]["hasFullVideo"] is False


def test_assets_are_whitelisted(client):
    assert client.get(f"/api/games/{KEY}/asset/result.jpg").content == b"jpg"
    assert client.get(f"/api/games/{KEY}/asset/game.json").status_code == 404
    assert client.get(f"/api/games/{KEY}/asset/portrait_me.jpg").status_code == 404


def test_pin_toggles(client):
    assert client.patch(f"/api/games/{KEY}", json={"pinned": True}).json()["pinned"] is True
    assert json.loads((client.tmp / "games" / KEY / "game.json").read_text(encoding="utf-8"))["pinned"] is True


def test_candidate_edit_dismiss_and_validation(client):
    url = f"/api/games/{KEY}/candidates/{KEY}_01"
    body = client.patch(url, json={"start": 95.0, "end": 150.0}).json()
    assert body["user"] == {"start": 95.0, "end": 150.0} and body["start"] == 100
    assert client.patch(url, json={"dismissed": True}).json()["user"]["dismissed"] is True
    assert client.patch(url, json={"start": 200.0}).status_code == 400
    assert client.patch(url, json={"savedClipId": "x"}).status_code == 400
    assert client.patch(f"/api/games/{KEY}/candidates/nope", json={"dismissed": True}).status_code == 404
    assert client.get("/api/games").json()["games"][0]["candidateCount"] == 1


def test_user_candidates_can_be_added_and_deleted(client):
    made = client.post(f"/api/games/{KEY}/candidates", json={"start": 400.0, "end": 430.0, "title": "내 구간"})
    assert made.status_code == 201 and made.json()["id"] == f"{KEY}_u1"
    assert client.post(f"/api/games/{KEY}/candidates", json={"start": 590.0, "end": 700.0}).status_code == 400
    assert client.get("/api/games").json()["games"][0]["candidateCount"] == 3
    assert client.delete(f"/api/games/{KEY}/candidates/{KEY}_u1").status_code == 200
    assert client.delete(f"/api/games/{KEY}/candidates/{KEY}_01").status_code == 404


def test_saving_a_candidate_creates_a_clip_the_existing_api_can_read(client):
    resp = client.post(f"/api/games/{KEY}/candidates/{KEY}_01/save")
    assert resp.status_code == 200 and resp.json()["clipId"] == f"{KEY}_01"
    assert any(c["id"] == f"{KEY}_01" for c in client.get("/api/clips").json())
    assert client.get(f"/api/games/{KEY}").json()["candidates"][0]["user"]["savedClipId"] == f"{KEY}_01"
    assert client.post(f"/api/games/{KEY}/candidates/{KEY}_01/save").json()["clipId"] == f"{KEY}_01"
    assert len(client.cuts) == 1  # 두 번째는 다시 자르지 않는다


def test_batch_save_modes(client):
    certain = client.post(f"/api/games/{KEY}/save", json={"mode": "certain"}).json()
    assert [s["candidateId"] for s in certain["saved"]] == [f"{KEY}_01"] and certain["failed"] == []
    rest = client.post(f"/api/games/{KEY}/save", json={"mode": "all"}).json()
    assert [s["candidateId"] for s in rest["saved"]] == [f"{KEY}_02"]
    assert client.post(f"/api/games/{KEY}/save", json={"mode": "weird"}).status_code == 400


def test_saving_without_a_full_video_is_a_conflict(client):
    (client.tmp / "games" / KEY / "full.mp4").unlink()
    assert client.post(f"/api/games/{KEY}/candidates/{KEY}_01/save").status_code == 409


def test_resaving_after_a_range_change_replaces_the_clip_and_unchanged_resave_does_nothing(client):
    url = f"/api/games/{KEY}/candidates/{KEY}_01"
    client.post(f"{url}/save")
    saved = client.get(f"/api/games/{KEY}").json()["candidates"][0]["user"]
    assert saved["savedStart"] == 100.0 and saved["savedEnd"] == 140.0

    client.post(f"{url}/save")
    assert len(client.cuts) == 1

    assert client.patch(url, json={"start": 90.0, "end": 150.0}).status_code == 200
    assert client.post(f"{url}/save").json()["clipId"] == f"{KEY}_01"
    assert len(client.cuts) == 2
    cmd = client.cuts[-1]
    assert cmd[cmd.index("-ss") + 1] == "90.000" and cmd[cmd.index("-t") + 1] == "60.000"
    user = client.get(f"/api/games/{KEY}").json()["candidates"][0]["user"]
    assert user["savedStart"] == 90.0 and user["savedEnd"] == 150.0 and user["savedClipId"] == f"{KEY}_01"
    assert len([c for c in client.get("/api/clips").json() if c["id"].startswith(KEY)]) == 1


def test_a_clip_saved_before_range_records_existed_counts_the_detected_range_as_saved(client):
    url = f"/api/games/{KEY}/candidates/{KEY}_01"
    client.post(f"{url}/save")
    path = client.tmp / "games" / KEY / "game.json"
    game = json.loads(path.read_text(encoding="utf-8"))
    game["candidates"][0]["user"] = {"savedClipId": f"{KEY}_01"}
    path.write_text(json.dumps(game), encoding="utf-8")
    client.post(f"{url}/save")
    assert len(client.cuts) == 1
    client.patch(url, json={"start": 95.0})
    client.post(f"{url}/save")
    assert len(client.cuts) == 2


def test_summary_counts_candidates_edited_but_not_saved(client):
    url = f"/api/games/{KEY}/candidates/{KEY}_01"
    assert client.get("/api/games").json()["games"][0]["unsavedEditCount"] == 0
    client.patch(url, json={"start": 95.0})
    assert client.get("/api/games").json()["games"][0]["unsavedEditCount"] == 1
    client.post(f"{url}/save")
    assert client.get("/api/games").json()["games"][0]["unsavedEditCount"] == 0
    client.patch(url, json={"end": 150.0})
    client.patch(f"/api/games/{KEY}/candidates/{KEY}_02", json={"start": 310.0})
    assert client.get("/api/games").json()["games"][0]["unsavedEditCount"] == 2
    client.patch(f"/api/games/{KEY}/candidates/{KEY}_02", json={"dismissed": True})
    assert client.get("/api/games").json()["games"][0]["unsavedEditCount"] == 1
