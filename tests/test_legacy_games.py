import json
from pathlib import Path

from lumia_briefing_room.pipeline import legacy_games as lg

START = "2026-09-28T16:00:25.975000Z"
SESSION = "bg_1_20260928_144503"
KEY = "20260928_160025"


def _clip(clips: Path, name: str, **over) -> None:
    meta = {
        "title": f"{name} 교전", "sessionDir": SESSION, "sessionStartUtc": "2026-09-28T15:45:00Z",
        "matchStartUtc": START, "matchEndUtc": "2026-09-28T16:18:00Z", "gameMode": "battle_royale",
        "sourceWidth": 2560, "sourceHeight": 1440, "videoOffsetSec": 1000.0, "durationSec": 27.0,
        "combatStartOffsetSec": 1005.0, "combatEndOffsetSec": 1015.0, "prerollSource": "combat",
        "tags": ["kill"], "killDelta": 1, "assistDelta": 0, "died": False, "pvpScore": 3.0, "pvpSignals": ["x"],
        "enemyRingMean": 0.5, "ultimateDelta": 0.1, "region": "바지선", "gameDay": 1, "dayNight": "day",
        "cobaltPhase": None, "detectorConfidence": 0.6, "matchKills": 2, "matchAssists": 1,
        "matchResult": {"placement": 3, "total": 8, "imagePath": ".thumbs/20260928_160025_result.jpg"},
        "myCharacterPortraitPath": ".thumbs/20260928_160025_portrait_me.jpg",
        "teammatePortraitPaths": [".thumbs/20260928_160025_portrait_teammate1.jpg"],
        "sourceIncomplete": False, "pinned": False,
    }
    meta.update(over)
    (clips / f"{name}.json").write_text(json.dumps(meta), encoding="utf-8")
    (clips / f"{name}.mp4").write_bytes(b"v")


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    clips, games = tmp_path / "clips", tmp_path / "games"
    (clips / ".thumbs").mkdir(parents=True)
    for n in ("result", "portrait_me", "portrait_teammate1"):
        (clips / ".thumbs" / f"20260928_160025_{n}.jpg").write_bytes(n.encode())
    _clip(clips, f"{KEY}_01", videoOffsetSec=1000.0, combatStartOffsetSec=1005.0, combatEndOffsetSec=1015.0)
    _clip(clips, f"{KEY}_02", title="둘째", tags=["death"], died=True, videoOffsetSec=1300.0,
          combatStartOffsetSec=1305.0, combatEndOffsetSec=1320.0)
    return clips, games


def test_merges_clips_of_one_game_into_one_game_json(tmp_path):
    clips, games = _setup(tmp_path)

    created = lg.migrate_legacy_games(clips, games)

    assert created == [KEY]
    game = json.loads((games / KEY / "game.json").read_text(encoding="utf-8"))
    assert game["gameKey"] == KEY and game["legacy"] is True and game["source"] == "steam"
    assert game["sessionDir"] == SESSION and game["matchStartUtc"] == START
    assert game["matchEndUtc"] == "2026-09-28T16:18:00Z" and game["gameMode"] == "battle_royale"
    assert game["matchKills"] == 2 and game["matchAssists"] == 1
    assert game["fullVideo"] is None and game["fullVideoError"] == lg.LEGACY_ERROR
    assert game["markers"] == [] and game["userCandidates"] == []


def test_a_result_the_user_locked_on_a_clip_stays_locked_on_the_game(tmp_path):
    clips, games = _setup(tmp_path)
    _clip(clips, f"{KEY}_01", matchResultSource="manual", matchResult={"placement": 1})

    lg.migrate_legacy_games(clips, games)

    game = json.loads((games / KEY / "game.json").read_text(encoding="utf-8"))
    assert game["matchResult"]["placement"] == 1 and game["matchResultSource"] == "manual"


def test_candidates_are_the_saved_clips(tmp_path):
    clips, games = _setup(tmp_path)
    lg.migrate_legacy_games(clips, games)

    game = json.loads((games / KEY / "game.json").read_text(encoding="utf-8"))
    first, second = game["candidates"]
    assert first["id"] == f"{KEY}_01" and first["user"] == {"savedClipId": f"{KEY}_01"}
    assert first["title"] == f"{KEY}_01 교전" and first["tags"] == ["kill"] and first["certain"] is True
    assert first["pvpScore"] == 3.0 and first["region"] == "바지선" and first["killDelta"] == 1
    assert second["died"] is True and second["user"] == {"savedClipId": f"{KEY}_02"}
    assert first["end"] - first["start"] == 27.0 and first["combatStart"] - first["start"] == 5.0
    assert first["start"] < second["start"]


def test_result_and_assets_are_copied_with_new_relative_paths(tmp_path):
    clips, games = _setup(tmp_path)
    lg.migrate_legacy_games(clips, games)

    folder = games / KEY
    game = json.loads((folder / "game.json").read_text(encoding="utf-8"))
    assert game["matchResult"]["placement"] == 3 and game["matchResult"]["imagePath"] == "result.jpg"
    assert (folder / "result.jpg").read_bytes() == b"result"
    assert game["portraits"] == {"me": "portrait_me.jpg", "teammate1": "portrait_teammate1.jpg", "teammate2": None}
    assert (folder / "portrait_me.jpg").read_bytes() == b"portrait_me"
    assert (clips / ".thumbs" / "20260928_160025_result.jpg").exists()  # 옛 파일은 지우지 않는다


def test_running_twice_gives_the_same_result_and_keeps_old_files(tmp_path):
    clips, games = _setup(tmp_path)
    lg.migrate_legacy_games(clips, games)
    before = (games / KEY / "game.json").read_bytes()

    assert lg.migrate_legacy_games(clips, games) == []

    assert (games / KEY / "game.json").read_bytes() == before
    assert (clips / f"{KEY}_01.json").exists() and (clips / f"{KEY}_01.mp4").exists()


def test_existing_game_json_is_never_touched(tmp_path):
    clips, games = _setup(tmp_path)
    (games / KEY).mkdir(parents=True)
    (games / KEY / "game.json").write_text('{"gameKey": "mine"}', encoding="utf-8")

    assert lg.migrate_legacy_games(clips, games) == []

    assert json.loads((games / KEY / "game.json").read_text(encoding="utf-8")) == {"gameKey": "mine"}


def test_folder_with_full_video_but_no_game_json_is_skipped(tmp_path):
    clips, games = _setup(tmp_path)
    (games / KEY).mkdir(parents=True)
    (games / KEY / "full.mp4").write_bytes(b"cutting")

    assert lg.migrate_legacy_games(clips, games) == []
    assert not (games / KEY / "game.json").exists()


def test_game_record_without_clips_becomes_a_game_with_no_candidates(tmp_path):
    clips, games = tmp_path / "clips", tmp_path / "games"
    records = clips / ".games"
    records.mkdir(parents=True)
    (records / "r.jpg").write_bytes(b"img")
    (records / "r.json").write_text(json.dumps({
        "id": "r", "sessionDir": SESSION, "matchStartUtc": START, "gameMode": "battle_royale",
        "matchResult": {"placement": 1, "total": 8, "imagePath": str(records / "r.jpg")},
    }), encoding="utf-8")

    assert lg.migrate_legacy_games(clips, games) == [KEY]

    game = json.loads((games / KEY / "game.json").read_text(encoding="utf-8"))
    assert game["candidates"] == [] and game["matchResult"]["imagePath"] == "result.jpg"
    assert (games / KEY / "result.jpg").read_bytes() == b"img"


def test_record_and_clips_of_the_same_game_merge_into_one(tmp_path):
    clips, games = _setup(tmp_path)
    records = clips / ".games"
    records.mkdir()
    (records / "r.json").write_text(json.dumps(
        {"sessionDir": SESSION, "matchStartUtc": START, "matchResult": {"placement": 9}}), encoding="utf-8")

    assert lg.migrate_legacy_games(clips, games) == [KEY]

    game = json.loads((games / KEY / "game.json").read_text(encoding="utf-8"))
    assert len(game["candidates"]) == 2 and game["matchResult"]["placement"] == 3  # 클립 쪽 결과를 우선


def test_different_matches_and_unreadable_files(tmp_path):
    clips, games = _setup(tmp_path)
    _clip(clips, "20260928_170000_01", matchStartUtc="2026-09-28T17:00:00Z", matchResult=None,
          myCharacterPortraitPath=None, teammatePortraitPaths=[])
    (clips / "broken.json").write_text("not json", encoding="utf-8")
    (clips / "nostart.json").write_text("{}", encoding="utf-8")

    assert sorted(lg.migrate_legacy_games(clips, games)) == ["20260928_160025", "20260928_170000"]

    other = json.loads((games / "20260928_170000" / "game.json").read_text(encoding="utf-8"))
    assert other["matchResult"] is None and other["portraits"] == {"me": None, "teammate1": None, "teammate2": None}


def test_missing_clips_dir_is_fine(tmp_path):
    assert lg.migrate_legacy_games(tmp_path / "nope", tmp_path / "games") == []


def test_games_list_migrates_old_clips_once(tmp_path):
    from fastapi.testclient import TestClient

    from lumia_briefing_room.api.app import create_app
    from lumia_briefing_room.config import Config, PathsConfig

    clips, games = _setup(tmp_path)
    cfg = Config(paths=PathsConfig(clips=clips, temp=tmp_path / "tmp", games=games))
    client = TestClient(create_app(cfg, config_path=tmp_path / "config.json"))

    (game,) = client.get("/api/games").json()["games"]

    assert game["key"] == KEY and game["legacy"] is True and game["hasFullVideo"] is False
    assert game["candidateCount"] == 2 and game["savedClipCount"] == 2
    assert game["fullVideoError"] == lg.LEGACY_ERROR
    assert len(client.get("/api/games").json()["games"]) == 1


def test_legacy_game_without_video_is_ignored_by_auto_clean(tmp_path):
    from lumia_briefing_room.config import RetentionConfig
    from lumia_briefing_room.pipeline.game_cleanup import plan_game_cleanup

    clips, games = _setup(tmp_path)
    lg.migrate_legacy_games(clips, games)

    plan = plan_game_cleanup(games, RetentionConfig(auto_clean_enabled=True, max_total_gb=0.000001))

    assert plan.to_delete == [] and (games / KEY / "game.json").exists()


def test_existing_clip_ids_of_a_legacy_game_near_the_window_start(tmp_path):
    clips, games = _setup(tmp_path)
    lg.migrate_legacy_games(clips, games)
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 9, 28, 16, 0, 25, 975000, tzinfo=timezone.utc)

    assert lg.existing_clip_ids(games, clips, start + timedelta(seconds=30)) == {f"{KEY}_01", f"{KEY}_02"}
    assert lg.existing_clip_ids(games, clips, start + timedelta(minutes=30)) is None
    (clips / f"{KEY}_02.json").unlink()
    assert lg.existing_clip_ids(games, clips, start) == {f"{KEY}_01"}



def _new_game(games: Path, key: str, cands: list[dict], *, offset: float = 925.0) -> None:
    folder = games / key
    folder.mkdir(parents=True)
    (folder / "full.mp4").write_bytes(b"v")
    (folder / "game.json").write_text(json.dumps({
        "gameKey": key, "matchStartUtc": "2026-09-28T15:59:25Z", "fullVideo": {"path": "full.mp4", "offsetSec": offset},
        "candidates": cands,
    }), encoding="utf-8")


def _cand(cid, combat_start, combat_end):
    return {"id": cid, "start": combat_start - 5, "end": combat_end + 5, "combatStart": combat_start, "combatEnd": combat_end, "user": {}}


def test_adopting_links_old_clips_to_the_new_candidates_that_overlap_and_supersedes_the_old_record(tmp_path):
    clips, games = _setup(tmp_path)
    lg.migrate_legacy_games(clips, games)
    legacy = json.loads((games / KEY / "game.json").read_text(encoding="utf-8"))
    # 옛 클립: 세션 기준 전투 1005~1015 / 1305~1320. 새 게임은 풀영상 0초 = 세션 925초
    _new_game(games, "20260928_155925", [_cand("20260928_155925_01", 1300 - 925, 1322 - 925), _cand("20260928_155925_02", 1003 - 925, 1014 - 925), _cand("x", 3000 - 925, 3010 - 925)])

    lg.adopt_legacy_clips(games, legacy, "20260928_155925")

    new = json.loads((games / "20260928_155925" / "game.json").read_text(encoding="utf-8"))
    assert [c["user"] for c in new["candidates"]] == [{"savedClipId": f"{KEY}_02"}, {"savedClipId": f"{KEY}_01"}, {}]
    assert json.loads((games / KEY / "game.json").read_text(encoding="utf-8"))["supersededBy"] == "20260928_155925"


def test_adopting_into_the_same_key_keeps_the_game_and_only_links_clips(tmp_path):
    clips, games = _setup(tmp_path)
    lg.migrate_legacy_games(clips, games)
    legacy = json.loads((games / KEY / "game.json").read_text(encoding="utf-8"))
    (games / KEY / "full.mp4").write_bytes(b"v")
    data = {**legacy, "legacy": None, "fullVideo": {"path": "full.mp4", "offsetSec": 925.975},
            "candidates": [_cand("other", 1005 - 925.975, 1015 - 925.975)]}
    (games / KEY / "game.json").write_text(json.dumps(data), encoding="utf-8")

    lg.adopt_legacy_clips(games, legacy, KEY)

    new = json.loads((games / KEY / "game.json").read_text(encoding="utf-8"))
    assert new["candidates"][0]["user"] == {"savedClipId": f"{KEY}_01"} and "supersededBy" not in new


def test_superseded_games_are_hidden_from_listings_and_are_not_legacy_matches(tmp_path):
    clips, games = _setup(tmp_path)
    lg.migrate_legacy_games(clips, games)
    from lumia_briefing_room.pipeline.game_files import list_games

    legacy = json.loads((games / KEY / "game.json").read_text(encoding="utf-8"))
    (games / KEY / "game.json").write_text(json.dumps({**legacy, "supersededBy": "20260928_155925"}), encoding="utf-8")

    assert list_games(games) == []
    assert lg.migrate_legacy_games(clips, games) == []  # 다시 옛 게임으로 되살아나지 않는다
