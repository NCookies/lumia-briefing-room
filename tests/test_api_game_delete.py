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


def test_deleting_a_clip_removes_the_video_and_the_candidate_entirely(client):
    client.post(f"/api/games/{KEY}/candidates/{KEY}_01/save")
    resp = client.post(f"/api/games/{KEY}/candidates/{KEY}_01/unsave")
    assert resp.status_code == 200 and resp.json() == {"id": f"{KEY}_01", "deleted": True}
    ids = [c["id"] for c in _game(client)["candidates"]]
    assert f"{KEY}_01" not in ids and f"{KEY}_02" in ids, "클립을 지우면 그 구간(후보)도 목록에서 사라진다"
    assert _clip_videos(client) == []


def test_deleting_the_clip_of_a_user_added_range_removes_that_range_too(client):
    made = client.post(f"/api/games/{KEY}/candidates", json={"start": 200.0, "end": 230.0}).json()
    client.post(f"/api/games/{KEY}/candidates/{made['id']}/save")
    assert _clip_videos(client)
    assert client.post(f"/api/games/{KEY}/candidates/{made['id']}/unsave").status_code == 200
    assert _game(client)["userCandidates"] == [] and _clip_videos(client) == []


def test_the_full_video_and_other_candidates_are_untouched_by_a_clip_delete(client):
    _save_all(client)
    client.post(f"/api/games/{KEY}/candidates/{KEY}_01/unsave")
    game = _game(client)
    assert game["hasFullVideo"] is True
    assert [c["user"].get("savedClipId") for c in game["candidates"]] == [f"{KEY}_02"]


def test_unsave_of_a_candidate_that_was_not_saved_is_a_conflict(client):
    assert client.post(f"/api/games/{KEY}/candidates/{KEY}_01/unsave").status_code == 409


def _seed_record(client):
    from lumia_briefing_room.pipeline.game_records import game_key, records_dir_for

    records = records_dir_for(client.library)
    records.mkdir(parents=True, exist_ok=True)
    path = records / f"{game_key('bg_1', '2026-09-30T00:24:00Z')}.json"
    path.write_text("{}", encoding="utf-8")
    return path


def test_deleting_the_whole_game_removes_the_row_the_files_and_the_game_record(client):
    _save_all(client)
    record = _seed_record(client)
    resp = client.post(f"/api/games/{KEY}/delete", json={"target": "all"})
    assert resp.status_code == 200 and resp.json()["deletedClips"] == 2 and resp.json()["deletedFullVideo"] is True
    assert client.get("/api/games").json()["games"] == []
    assert client.get(f"/api/games/{KEY}").status_code == 404
    assert not (client.tmp / "games" / KEY).exists() and _clip_videos(client) == []
    assert not record.exists(), "기록이 남으면 앱을 다시 켤 때 이전 버전 게임으로 되살아난다"


def test_deleting_the_whole_game_also_works_when_nothing_else_is_left(client):
    client.post(f"/api/games/{KEY}/delete", json={"target": "both"})
    assert client.post(f"/api/games/{KEY}/delete", json={"target": "all"}).status_code == 200
    assert client.get("/api/games").json()["games"] == []


def test_clips_deleted_with_the_whole_game_do_not_leave_a_new_game_record(client):
    from lumia_briefing_room.pipeline.game_records import records_dir_for

    _save_all(client)
    client.post(f"/api/games/{KEY}/delete", json={"target": "all"})
    records = records_dir_for(client.library)
    assert not records.exists() or list(records.glob("*.json")) == []
