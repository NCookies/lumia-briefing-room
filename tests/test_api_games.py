import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api import game_routes
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig, resolve_paths
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
    c.library = resolve_paths(cfg.paths).library_steam
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


def _game_json(client):
    return json.loads((client.tmp / "games" / KEY / "game.json").read_text(encoding="utf-8"))


def test_game_title_is_saved_trimmed_and_cleared_by_an_empty_value(client):
    assert client.get("/api/games").json()["games"][0]["title"] is None
    assert client.patch(f"/api/games/{KEY}", json={"title": "  첫 우승  "}).json()["title"] == "첫 우승"
    assert _game_json(client)["title"] == "첫 우승"
    assert client.get(f"/api/games/{KEY}").json()["title"] == "첫 우승"
    assert client.patch(f"/api/games/{KEY}", json={"title": "  "}).json()["title"] is None
    assert _game_json(client)["title"] is None
    assert client.patch(f"/api/games/{KEY}", json={"title": "가" * 61}).status_code == 400


def test_patching_other_fields_does_not_touch_the_title(client):
    client.patch(f"/api/games/{KEY}", json={"title": "유지"})
    client.patch(f"/api/games/{KEY}", json={"pinned": True})
    assert _game_json(client)["title"] == "유지"


def test_editing_the_result_locks_it_on_the_game(client):
    body = client.patch(
        f"/api/games/{KEY}", json={"matchResult": {"placement": 3, "matchType": "rank", "tk": 10, "kills": 4, "assists": 2}}
    ).json()
    assert body["matchResult"]["placement"] == 3 and body["matchResult"]["tk"] == 10
    assert body["matchResultSource"] == "manual"
    saved = _game_json(client)
    assert saved["matchResult"]["imagePath"] == "result.jpg" and saved["matchResultSource"] == "manual"


def test_a_bad_result_edit_is_rejected_and_changes_nothing(client):
    assert client.patch(f"/api/games/{KEY}", json={"matchResult": {"placement": 0}}).status_code == 400
    assert client.patch(f"/api/games/{KEY}", json={"matchResult": {"imagePath": "x"}}).status_code == 400
    assert client.patch(f"/api/games/{KEY}", json={"matchResult": {"placement": 2}, "title": "가" * 61}).status_code == 400
    saved = _game_json(client)
    assert saved["matchResult"]["placement"] == 1 and "matchResultSource" not in saved


def test_the_lock_cannot_be_removed_through_the_api(client):
    client.patch(f"/api/games/{KEY}", json={"matchResult": {"placement": 5}})
    body = client.patch(f"/api/games/{KEY}", json={"matchResultSource": None}).json()
    assert body["matchResultSource"] == "manual" and body["matchResult"]["placement"] == 5


def test_a_cobalt_game_only_takes_victory_or_defeat(client):
    path = client.tmp / "games" / KEY / "game.json"
    game = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**game, "gameMode": "cobalt", "matchResult": {"outcome": "패배"}}), encoding="utf-8")
    assert client.patch(f"/api/games/{KEY}", json={"matchResult": {"outcome": "실험 종료"}}).status_code == 400
    assert client.patch(f"/api/games/{KEY}", json={"matchResult": {"outcome": "승리"}}).json()["matchResult"]["outcome"] == "승리"


def test_editing_the_result_updates_the_clips_made_from_the_game_too(client):
    client.post(f"/api/games/{KEY}/candidates/{KEY}_01/save")
    client.patch(f"/api/games/{KEY}", json={"matchResult": {"placement": 2, "kills": 7}})
    meta = json.loads((client.library / f"{KEY}_01.json").read_text(encoding="utf-8"))
    assert meta["matchResult"]["placement"] == 2 and meta["matchResult"]["kills"] == 7
    assert meta["matchResultSource"] == "manual"
    clip = next(c for c in client.get("/api/clips").json() if c["id"] == f"{KEY}_01")
    assert clip["matchResult"]["placement"] == 2


def test_a_clip_saved_after_the_edit_carries_the_locked_result(client):
    client.patch(f"/api/games/{KEY}", json={"matchResult": {"placement": 4}})
    client.post(f"/api/games/{KEY}/candidates/{KEY}_02/save")
    meta = json.loads((client.library / f"{KEY}_02.json").read_text(encoding="utf-8"))
    assert meta["matchResult"]["placement"] == 4 and meta["matchResultSource"] == "manual"


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


def test_summary_counts_only_archived_candidates_edited_after_saving(client):
    url = f"/api/games/{KEY}/candidates/{KEY}_01"
    other = f"/api/games/{KEY}/candidates/{KEY}_02"
    assert client.get("/api/games").json()["games"][0]["unsavedEditCount"] == 0
    client.patch(url, json={"start": 95.0})
    assert client.get("/api/games").json()["games"][0]["unsavedEditCount"] == 0, "보관하지 않은 후보의 수정은 바로 기억되므로 저장 대기가 아니다"
    client.post(f"{url}/save")
    assert client.get("/api/games").json()["games"][0]["unsavedEditCount"] == 0
    client.patch(url, json={"end": 150.0})
    client.patch(other, json={"start": 310.0})
    assert client.get("/api/games").json()["games"][0]["unsavedEditCount"] == 1
    client.post(f"{other}/save")
    client.patch(other, json={"start": 305.0})
    assert client.get("/api/games").json()["games"][0]["unsavedEditCount"] == 2
    client.patch(other, json={"dismissed": True})
    assert client.get("/api/games").json()["games"][0]["unsavedEditCount"] == 1


def test_renaming_a_saved_candidate_renames_its_clip_without_recutting(client):
    url = f"/api/games/{KEY}/candidates/{KEY}_01"
    client.post(f"{url}/save")
    assert client.patch(url, json={"title": "멋진 교전"}).json()["user"]["title"] == "멋진 교전"
    meta = json.loads((client.library / f"{KEY}_01.json").read_text(encoding="utf-8"))
    assert meta["title"] == "멋진 교전"
    client.post(f"{url}/save")
    assert len(client.cuts) == 1


def test_a_renamed_candidate_is_saved_under_the_new_title(client):
    url = f"/api/games/{KEY}/candidates/{KEY}_02"
    client.patch(url, json={"title": "내 이름"})
    client.post(f"{url}/save")
    meta = json.loads((client.library / f"{KEY}_02.json").read_text(encoding="utf-8"))
    assert meta["title"] == "내 이름"


def test_portrait_files_left_in_the_folder_are_shown_even_if_game_json_lost_the_names(client):
    folder = client.tmp / "games" / KEY
    (folder / "portrait_me.jpg").write_bytes(b"me")
    (folder / "portrait_teammate2.jpg").write_bytes(b"mate")
    (game,) = client.get("/api/games").json()["games"]
    assert game["portraits"]["me"] == "portrait_me.jpg" and game["portraits"]["teammate2"] == "portrait_teammate2.jpg"
    assert game["portraits"].get("teammate1") is None
    detail = client.get(f"/api/games/{KEY}").json()
    assert detail["portraits"]["me"] == "portrait_me.jpg"
    assert client.get(f"/api/games/{KEY}/asset/portrait_me.jpg").content == b"me"


def test_cobalt_games_never_show_leftover_portrait_files(client):
    folder = client.tmp / "games" / KEY
    game = json.loads((folder / "game.json").read_text(encoding="utf-8"))
    game["gameMode"] = "cobalt"
    (folder / "game.json").write_text(json.dumps(game), encoding="utf-8")
    (folder / "portrait_me.jpg").write_bytes(b"me")
    (game,) = client.get("/api/games").json()["games"]
    assert not any(game["portraits"].values())
    assert not any(client.get(f"/api/games/{KEY}").json()["portraits"].values())


def test_a_game_recorded_before_the_steam_recording_stopped_is_flagged_with_the_cause(client):
    from lumia_briefing_room.pipeline.recording_stop import STOPPED_BEFORE_MESSAGE

    folder = client.tmp / "games" / KEY
    game = json.loads((folder / "game.json").read_text(encoding="utf-8"))
    game.update(fullVideo=None, fullVideoError="세그먼트를 찾을 수 없다: 680-1180", candidates=[], matchResult=None)
    (folder / "game.json").write_text(json.dumps(game), encoding="utf-8")
    (folder / "full.mp4").unlink()

    (row,) = client.get("/api/games").json()["games"]
    assert row["recordingStopped"] == "before" and row["fullVideoError"] == STOPPED_BEFORE_MESSAGE
    detail = client.get(f"/api/games/{KEY}").json()
    assert detail["recordingStopped"] == "before" and detail["fullVideoError"] == STOPPED_BEFORE_MESSAGE


def test_a_normal_game_is_not_flagged(client):
    (row,) = client.get("/api/games").json()["games"]
    assert row["recordingStopped"] is None


def test_list_resolves_saved_clip_videos_in_one_pass(client, monkeypatch):
    from lumia_briefing_room.api import clips as clips_api

    for cid in (f"{KEY}_01", f"{KEY}_02"):
        client.post(f"/api/games/{KEY}/candidates/{cid}/save")
    calls = []
    real = clips_api.link_all
    monkeypatch.setattr(clips_api, "link_all", lambda *a, **kw: (calls.append(1), real(*a, **kw))[1])
    (game,) = client.get("/api/games").json()["games"]
    assert game["savedClipCount"] == 2
    assert len(calls) == 1, "클립마다 클립 폴더를 다시 훑으면 게임·클립이 늘수록 목록이 느려진다"
    detail = client.get(f"/api/games/{KEY}").json()
    assert all(c["user"].get("savedClipId") for c in detail["candidates"])
    assert len(calls) == 2


def test_clip_source_finds_the_game_and_candidate_a_clip_was_saved_from(client):
    clip_id = client.post(f"/api/games/{KEY}/candidates/{KEY}_02/save").json()["clipId"]
    body = client.get(f"/api/games/by-clip/{clip_id}").json()
    assert body == {"gameKey": KEY, "candidateId": f"{KEY}_02", "source": "steam", "hasFullVideo": True}


def test_clip_source_reports_a_deleted_full_video_and_404_for_unlinked_clips(client):
    clip_id = client.post(f"/api/games/{KEY}/candidates/{KEY}_01/save").json()["clipId"]
    (client.tmp / "games" / KEY / "full.mp4").unlink()
    assert client.get(f"/api/games/by-clip/{clip_id}").json()["hasFullVideo"] is False
    assert client.get("/api/games/by-clip/not-a-clip").status_code == 404


def _titles(client, q):
    return client.get("/api/games", params={"q": q}).json()["games"]


def test_search_without_a_query_lists_everything_without_match_info(client):
    (game,) = client.get("/api/games").json()["games"]
    assert "match" not in game
    assert len(_titles(client, "")) == 1 and len(_titles(client, "   ")) == 1


def test_search_by_game_title_ignores_case_and_spaces(client):
    client.patch(f"/api/games/{KEY}", json={"title": "첫 우승 Run"})
    (game,) = _titles(client, "첫우승run")
    assert game["match"] == {"where": "게임 제목", "text": "첫 우승 Run"}
    assert _titles(client, "두번째") == []


def test_search_by_candidate_title_uses_the_edited_title_and_skips_dismissed(client):
    client.patch(f"/api/games/{KEY}/candidates/{KEY}_02", json={"title": "마지막 교전"})
    (game,) = _titles(client, "마지막")
    assert game["match"] == {"where": "후보", "text": "마지막 교전"}
    client.patch(f"/api/games/{KEY}/candidates/{KEY}_02", json={"dismissed": True})
    assert _titles(client, "마지막") == []


def test_search_by_saved_clip_memo(client):
    client.post(f"/api/games/{KEY}/candidates/{KEY}_01/save")
    client.patch(f"/api/clips/{KEY}_01", json={"memo": "궁극기 타이밍이 좋았다"})
    (game,) = _titles(client, "타이밍")
    assert game["match"] == {"where": "메모", "text": "궁극기 타이밍이 좋았다"}


def test_search_by_clip_title_that_differs_from_the_candidate(client):
    client.post(f"/api/games/{KEY}/candidates/{KEY}_01/save")
    client.patch(f"/api/clips/{KEY}_01", json={"title": "역전극"})
    (game,) = _titles(client, "역전")
    assert game["match"] == {"where": "클립", "text": "역전극"}


def test_search_by_streamer_and_video_name_for_vod_games(client):
    path = client.tmp / "games" / KEY / "game.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**data, "streamer": "홍길동", "vodFile": "D:/방송/Day3 Stream.mp4"}), encoding="utf-8")
    assert _titles(client, "홍길")[0]["match"] == {"where": "스트리머", "text": "홍길동"}
    assert _titles(client, "day3stream")[0]["match"] == {"where": "영상 이름", "text": "Day3 Stream.mp4"}
