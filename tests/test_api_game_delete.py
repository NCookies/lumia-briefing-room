import pytest
from test_api_games import KEY, client  # noqa: F401  (같은 게임 픽스처를 쓴다)


@pytest.fixture(autouse=True)
def permanent_delete(client):
    client.put("/api/config", json={"ui": {"deleteMode": "permanent"}})


def _game(client):
    return client.get(f"/api/games/{KEY}").json()


def _save_all(client):
    client.post(f"/api/games/{KEY}/save", json={"mode": "all"})


def _clip_videos(client):
    return sorted(p.name for p in (client.tmp / "clips").rglob("*.mp4"))


def test_deleting_only_the_full_video_keeps_clips_and_the_game_record(client):
    _save_all(client)
    resp = client.post(f"/api/games/{KEY}/delete", json={"target": "fullVideo"})
    assert resp.status_code == 200
    assert resp.json() == {"deletedFullVideo": True, "deletedClips": 0, "freedBytes": 1000}
    game = _game(client)
    assert game["hasFullVideo"] is False and game["fullVideoDeletedAt"]
    assert all(c["user"].get("savedClipId") for c in game["candidates"])
    assert len(_clip_videos(client)) == 2


def test_deleting_only_clips_keeps_the_full_video_and_clears_saved_marks(client):
    _save_all(client)
    resp = client.post(f"/api/games/{KEY}/delete", json={"target": "clips"})
    assert resp.json()["deletedClips"] == 2 and resp.json()["deletedFullVideo"] is False
    game = _game(client)
    assert game["hasFullVideo"] is True
    for cand in game["candidates"]:
        assert "savedClipId" not in cand["user"] and "savedStart" not in cand["user"]
    assert _clip_videos(client) == []
    assert client.get("/api/clips").json() == [] or client.get("/api/clips").json().get("clips") == []


def test_deleting_both(client):
    _save_all(client)
    resp = client.post(f"/api/games/{KEY}/delete", json={"target": "both"}).json()
    assert resp["deletedFullVideo"] is True and resp["deletedClips"] == 2
    assert _game(client)["hasFullVideo"] is False and _clip_videos(client) == []


def test_deleting_a_missing_full_video_is_a_conflict_but_both_still_removes_clips(client):
    _save_all(client)
    client.post(f"/api/games/{KEY}/delete", json={"target": "fullVideo"})
    assert client.post(f"/api/games/{KEY}/delete", json={"target": "fullVideo"}).status_code == 409
    resp = client.post(f"/api/games/{KEY}/delete", json={"target": "both"})
    assert resp.status_code == 200 and resp.json()["deletedFullVideo"] is False and resp.json()["deletedClips"] == 2


def test_clips_that_were_already_removed_elsewhere_are_just_unmarked(client):
    _save_all(client)
    for video in (client.tmp / "clips").rglob("*.mp4"):
        video.unlink()
    resp = client.post(f"/api/games/{KEY}/delete", json={"target": "clips"}).json()
    assert resp["deletedClips"] == 0
    assert all("savedClipId" not in c["user"] for c in _game(client)["candidates"])


def test_unknown_target_and_unknown_game(client):
    assert client.post(f"/api/games/{KEY}/delete", json={"target": "everything"}).status_code == 400
    assert client.post("/api/games/20990101_000000/delete", json={"target": "both"}).status_code == 404


def test_unsave_deletes_the_clip_and_dismisses_the_candidate(client):
    client.post(f"/api/games/{KEY}/candidates/{KEY}_01/save")
    resp = client.post(f"/api/games/{KEY}/candidates/{KEY}_01/unsave")
    assert resp.status_code == 200
    cand = _game(client)["candidates"][0]
    assert "savedClipId" not in cand["user"] and cand["user"]["dismissed"] is True
    assert _clip_videos(client) == []


def test_unsave_of_a_candidate_that_was_not_saved_is_a_conflict(client):
    assert client.post(f"/api/games/{KEY}/candidates/{KEY}_01/unsave").status_code == 409
