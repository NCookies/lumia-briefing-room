import pytest
from test_api_categories import KEY as CKEY
from test_api_categories import client as cat_client  # noqa: F401  (카테고리 폴더가 있는 저장소)
from test_api_categories import save as cat_save
from test_api_categories import videos as cat_videos
from test_api_games import KEY, client  # noqa: F401  (같은 게임 픽스처를 쓴다)


@pytest.fixture(autouse=True)
def permanent_delete(request):
    for name in ("client", "cat_client"):
        if name in request.fixturenames:
            request.getfixturevalue(name).put("/api/config", json={"ui": {"deleteMode": "permanent"}})


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
    assert resp.json() == {"deletedFullVideo": True, "deletedClips": 0, "keptClips": 0, "freedBytes": 1000}
    game = _game(client)
    assert game["hasFullVideo"] is False and game["fullVideoDeletedAt"]
    assert all(c["user"].get("savedClipId") for c in game["candidates"])
    assert len(_clip_videos(client)) == 2


def _cat_game(client):
    return client.get(f"/api/games/{CKEY}").json()


def _save_auto(client, *ids):
    for cid in ids:
        cat_save(client, cid, category="자동 보관")


def test_deleting_only_clips_keeps_the_full_video_and_clears_saved_marks(cat_client):
    _save_auto(cat_client, "01", "02")
    resp = cat_client.post(f"/api/games/{CKEY}/delete", json={"target": "clips"})
    assert resp.json()["deletedClips"] == 2 and resp.json()["deletedFullVideo"] is False
    game = _cat_game(cat_client)
    assert game["hasFullVideo"] is True
    for cand in game["candidates"]:
        assert "savedClipId" not in cand["user"] and "savedStart" not in cand["user"]
    assert cat_videos(cat_client, "자동 보관") == []


def test_deleting_both(cat_client):
    _save_auto(cat_client, "01", "02")
    resp = cat_client.post(f"/api/games/{CKEY}/delete", json={"target": "both"}).json()
    assert resp["deletedFullVideo"] is True and resp["deletedClips"] == 2
    assert _cat_game(cat_client)["hasFullVideo"] is False and cat_videos(cat_client, "자동 보관") == []


def test_deleting_a_missing_full_video_is_a_conflict_but_both_still_removes_clips(cat_client):
    _save_auto(cat_client, "01", "02")
    cat_client.post(f"/api/games/{CKEY}/delete", json={"target": "fullVideo"})
    assert cat_client.post(f"/api/games/{CKEY}/delete", json={"target": "fullVideo"}).status_code == 409
    resp = cat_client.post(f"/api/games/{CKEY}/delete", json={"target": "both"})
    assert resp.status_code == 200 and resp.json()["deletedFullVideo"] is False and resp.json()["deletedClips"] == 2


def _seed_mixed(client):
    cat_save(client, "01", category="자동 보관")
    cat_save(client, "02", category="아야")
    cat_save(client, "03")


def test_clip_delete_removes_only_auto_archive_clips_and_keeps_the_user_archived_ones(cat_client):
    _seed_mixed(cat_client)
    resp = cat_client.post(f"/api/games/{CKEY}/delete", json={"target": "clips"}).json()
    assert resp["deletedClips"] == 1 and resp["keptClips"] == 2
    assert cat_videos(cat_client, "자동 보관") == []
    assert cat_videos(cat_client, "아야") == [f"{CKEY}_02.mp4"] and cat_videos(cat_client, "보관함") == [f"{CKEY}_03.mp4"]
    cands = {c["id"]: c["user"] for c in _cat_game(cat_client)["candidates"]}
    assert "savedClipId" not in cands[f"{CKEY}_01"], "지운 클립의 표시만 뗀다"
    assert cands[f"{CKEY}_02"]["savedClipId"] == f"{CKEY}_02" and cands[f"{CKEY}_03"]["savedClipId"] == f"{CKEY}_03"
    assert cands[f"{CKEY}_02"]["archived"] is True


def test_both_target_deletes_the_full_video_and_auto_clips_but_keeps_archived_ones(cat_client):
    _seed_mixed(cat_client)
    resp = cat_client.post(f"/api/games/{CKEY}/delete", json={"target": "both"}).json()
    assert resp["deletedFullVideo"] is True and resp["deletedClips"] == 1
    assert len(cat_videos(cat_client, "아야")) == 1 and len(cat_videos(cat_client, "보관함")) == 1


def test_legacy_layout_clips_are_all_treated_as_archived_and_survive_clip_delete(client):
    _save_all(client)
    resp = client.post(f"/api/games/{KEY}/delete", json={"target": "clips"}).json()
    assert resp["deletedClips"] == 0 and resp["keptClips"] == 2 and len(_clip_videos(client)) == 2
    assert all(c["user"].get("savedClipId") for c in _game(client)["candidates"])


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

    records = records_dir_for(client.resolved.library_steam)
    records.mkdir(parents=True, exist_ok=True)
    path = records / f"{game_key('bg_1', '2026-09-30T00:24:00Z')}.json"
    path.write_text("{}", encoding="utf-8")
    return path


def test_deleting_the_whole_game_removes_the_row_the_files_and_the_game_record(cat_client):
    _save_auto(cat_client, "01", "02")
    record = _seed_record(cat_client)
    resp = cat_client.post(f"/api/games/{CKEY}/delete", json={"target": "all"})
    assert resp.status_code == 200 and resp.json()["deletedClips"] == 2 and resp.json()["deletedFullVideo"] is True
    assert cat_client.get("/api/games").json()["games"] == []
    assert cat_client.get(f"/api/games/{CKEY}").status_code == 404
    assert not (cat_client.resolved.games_steam / CKEY).exists() and cat_videos(cat_client, "자동 보관") == []
    assert not record.exists(), "기록이 남으면 앱을 다시 켤 때 이전 버전 게임으로 되살아난다"


def test_deleting_the_whole_game_also_works_when_nothing_else_is_left(client):
    client.post(f"/api/games/{KEY}/delete", json={"target": "both"})
    assert client.post(f"/api/games/{KEY}/delete", json={"target": "all"}).status_code == 200
    assert client.get("/api/games").json()["games"] == []


def test_clips_deleted_with_the_whole_game_do_not_leave_a_new_game_record(cat_client):
    from lumia_briefing_room.pipeline.game_records import records_dir_for

    _save_auto(cat_client, "01", "02")
    cat_client.post(f"/api/games/{CKEY}/delete", json={"target": "all"})
    records = records_dir_for(cat_client.resolved.library_steam)
    assert not records.exists() or list(records.glob("*.json")) == []


def test_whole_game_delete_removes_the_game_and_auto_clips_but_leaves_archived_clips_in_the_clip_tab(cat_client):
    _seed_mixed(cat_client)
    resp = cat_client.post(f"/api/games/{CKEY}/delete", json={"target": "all"})
    assert resp.status_code == 200 and resp.json()["deletedClips"] == 1 and resp.json()["keptClips"] == 2
    assert resp.json()["deletedFullVideo"] is True
    assert cat_client.get(f"/api/games/{CKEY}").status_code == 404
    assert cat_videos(cat_client, "자동 보관") == []
    ids = {c["id"] for c in cat_client.get("/api/clips").json()}
    assert ids == {f"{CKEY}_02", f"{CKEY}_03"}, "게임 기록이 사라져도 남은 클립은 클립 탭에 보인다"
    for cid in ids:
        assert cat_client.get(f"/api/clips/{cid}").status_code == 200
        assert cat_client.get(f"/api/clips/{cid}/video").status_code in (200, 206)
    assert cat_client.delete(f"/api/clips/{CKEY}_02").status_code == 200, "클립 탭에서 지울 수 있다"
    assert {c["id"] for c in cat_client.get("/api/clips").json()} == {f"{CKEY}_03"}


def test_whole_game_delete_removes_all_clips_when_every_clip_is_auto_archive(cat_client):
    _save_auto(cat_client, "01", "02")
    resp = cat_client.post(f"/api/games/{CKEY}/delete", json={"target": "all"}).json()
    assert resp["deletedClips"] == 2 and resp["keptClips"] == 0
    assert cat_client.get("/api/clips").json() == []


def test_whole_game_delete_keeps_every_clip_in_legacy_layout(client):
    client.get("/api/games")
    _save_all(client)
    resp = client.post(f"/api/games/{KEY}/delete", json={"target": "all"}).json()
    assert resp["deletedClips"] == 0 and resp["keptClips"] == 2 and len(_clip_videos(client)) == 2
    assert client.get("/api/games").json()["games"] == []



def test_a_deleted_game_does_not_come_back_after_a_restart_even_with_kept_clips(cat_client):
    from lumia_briefing_room.pipeline.legacy_games import migrate_legacy_games

    _seed_mixed(cat_client)
    cat_client.post(f"/api/games/{CKEY}/delete", json={"target": "all"})
    resolved = cat_client.resolved
    assert migrate_legacy_games(resolved.library_steam, resolved.games_steam) == []
    assert cat_client.get("/api/games").json()["games"] == []
    assert {c["id"] for c in cat_client.get("/api/clips").json()} == {f"{CKEY}_02", f"{CKEY}_03"}


def _lock_full_video(monkeypatch, failures):
    """다른 프로세스가 full.mp4 를 잡고 있는 것처럼 unlink 가 `failures` 번 PermissionError(WinError 32)를 낸다. failures=None 이면 계속."""
    import pathlib

    from lumia_briefing_room.pipeline import delete_helper

    monkeypatch.setattr(delete_helper, "LOCK_RETRY_DELAY_SEC", 0)
    real = pathlib.Path.unlink
    state = {"left": failures}

    def unlink(self, *args, **kwargs):
        if self.name == "full.mp4" and (state["left"] is None or state["left"] > 0):
            if state["left"] is not None:
                state["left"] -= 1
            raise PermissionError(32, "다른 프로세스가 파일을 사용 중입니다")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "unlink", unlink)


def test_whole_game_delete_waits_out_a_briefly_locked_full_video(client, monkeypatch):
    _lock_full_video(monkeypatch, failures=2)
    resp = client.post(f"/api/games/{KEY}/delete", json={"target": "all"})
    assert resp.status_code == 200
    assert client.get(f"/api/games/{KEY}").status_code == 404
    assert not (client.tmp / "games" / KEY).exists()


def test_whole_game_delete_with_a_locked_video_is_a_409_and_the_game_stays_deletable(client, monkeypatch):
    _lock_full_video(monkeypatch, failures=None)
    resp = client.post(f"/api/games/{KEY}/delete", json={"target": "all"})
    assert resp.status_code == 409 and "사용 중" in resp.json()["detail"]
    assert (client.tmp / "games" / KEY / "game.json").exists(), "게임 기록이 먼저 지워지면 다시 지울 수 없다"
    assert client.get(f"/api/games/{KEY}").status_code == 200
    monkeypatch.undo()
    client.put("/api/config", json={"ui": {"deleteMode": "permanent"}})
    assert client.post(f"/api/games/{KEY}/delete", json={"target": "all"}).status_code == 200
    assert client.get(f"/api/games/{KEY}").status_code == 404
