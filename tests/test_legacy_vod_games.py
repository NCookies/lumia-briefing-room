import json

from PIL import Image

from lumia_briefing_room.pipeline.legacy_vod_games import migrate_legacy_vod_games

VOD = "3df9b3313b4e"


def jpg(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), (10, 20, 30)).save(path)


def make_vod(tmp_path, *, clips_in_game2=True):
    root = tmp_path / "vod"
    (root / ".vods").mkdir(parents=True)
    ids = [f"vod_{VOD}_g01_000100", f"vod_{VOD}_g01_000300"]
    for n, clip_id in enumerate(ids):
        meta = {
            "title": f"클립 {n}", "source": "vod", "vodId": VOD, "vodGameIndex": 1,
            "videoOffsetSec": 100.0 + 200 * n, "durationSec": 40.0,
            "combatStartOffsetSec": 110.0 + 200 * n, "combatEndOffsetSec": 130.0 + 200 * n,
            "tags": ["kill"] if n == 0 else [], "pvpScore": 0.7, "gameDay": 2, "dayNight": "day", "region": "묘지",
            "pinned": n == 1,
            "matchResult": {"placement": 1, "total": 7, "imagePath": f".thumbs/{VOD}_g01_result.jpg"},
            "myCharacterPortraitPath": f".thumbs/{VOD}_g01_portrait_me.jpg",
            "teammatePortraitPaths": [f".thumbs/{VOD}_g01_portrait_teammate1.jpg"],
        }
        (root / f"{clip_id}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        (root / f"{clip_id}.mp4").write_bytes(b"x")
    jpg(root / ".thumbs" / f"{VOD}_g01_result.jpg")
    jpg(root / ".thumbs" / f"{VOD}_g01_portrait_me.jpg")
    jpg(root / ".thumbs" / f"{VOD}_g01_portrait_teammate1.jpg")
    jpg(root / ".thumbs" / f"{VOD}_g02_result.jpg")
    index = {
        "id": VOD, "path": "D:\\vod\\방송.mp4", "streamer": "하이용가리", "width": 1920, "height": 1080,
        "status": "done",
        "games": [
            {"index": 1, "startSec": 90.0, "endSec": 600.0, "kFinal": 3, "aFinal": 1, "gameMode": "battle_royale",
             "result": {"placement": 1, "total": 7, "imagePath": f".thumbs/{VOD}_g01_result.jpg"}, "clipIds": ids},
            {"index": 2, "startSec": 700.0, "endSec": 900.0, "kFinal": 0, "aFinal": 0, "gameMode": "battle_royale",
             "result": {"placement": 5, "total": 7, "imagePath": f".thumbs/{VOD}_g02_result.jpg"}, "clipIds": []},
        ],
    }
    (root / ".vods" / f"{VOD}.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return root, ids


def read(games, key):
    return json.loads((games / key / "game.json").read_text(encoding="utf-8"))


def test_each_analyzed_game_becomes_a_legacy_game_record_with_its_saved_clips(tmp_path):
    root, ids = make_vod(tmp_path)
    games = tmp_path / "games"

    created = migrate_legacy_vod_games(root, games)

    assert created == [f"vod_{VOD}_g01", f"vod_{VOD}_g02"]
    data = read(games, f"vod_{VOD}_g01")
    assert data["legacy"] is True and data["source"] == "vod" and data["vodId"] == VOD
    assert data["fullVideo"] is None and "풀영상이 없습니다" in data["fullVideoError"]
    assert [c["id"] for c in data["candidates"]] == ids
    assert [c["user"]["savedClipId"] for c in data["candidates"]] == ids
    assert data["candidates"][0]["start"] == 10.0 and data["candidates"][0]["certain"] is True
    assert data["matchKills"] == 3 and data["matchResult"]["placement"] == 1
    assert data["pinned"] is True and data["streamer"] == "하이용가리"


def test_result_and_portraits_are_copied_into_the_game_folder(tmp_path):
    root, _ = make_vod(tmp_path)
    games = tmp_path / "games"

    migrate_legacy_vod_games(root, games)

    data = read(games, f"vod_{VOD}_g01")
    folder = games / f"vod_{VOD}_g01"
    assert data["matchResult"]["imagePath"] == "result.jpg" and (folder / "result.jpg").is_file()
    assert data["portraits"] == {"me": "portrait_me.jpg", "teammate1": "portrait_teammate1.jpg", "teammate2": None}
    assert (folder / "portrait_me.jpg").is_file()


def test_a_game_without_clips_still_gets_a_record_with_its_result(tmp_path):
    root, _ = make_vod(tmp_path)
    games = tmp_path / "games"

    migrate_legacy_vod_games(root, games)

    data = read(games, f"vod_{VOD}_g02")
    assert data["candidates"] == [] and data["matchResult"]["placement"] == 5
    assert (games / f"vod_{VOD}_g02" / "result.jpg").is_file()


def test_running_twice_gives_the_same_result_and_keeps_old_files(tmp_path):
    root, ids = make_vod(tmp_path)
    games = tmp_path / "games"
    migrate_legacy_vod_games(root, games)
    before = (games / f"vod_{VOD}_g01" / "game.json").read_bytes()

    assert migrate_legacy_vod_games(root, games) == []

    assert (games / f"vod_{VOD}_g01" / "game.json").read_bytes() == before
    assert all((root / f"{cid}.json").is_file() and (root / f"{cid}.mp4").is_file() for cid in ids)


def test_games_that_already_have_a_record_or_a_full_video_are_left_alone(tmp_path):
    root, _ = make_vod(tmp_path)
    games = tmp_path / "games"
    done = games / f"vod_{VOD}_g01"
    done.mkdir(parents=True)
    (done / "game.json").write_text('{"gameKey": "keep"}', encoding="utf-8")
    cutting = games / f"vod_{VOD}_g02"
    cutting.mkdir()
    (cutting / "full.mp4").write_bytes(b"partial")

    assert migrate_legacy_vod_games(root, games) == []
    assert json.loads((done / "game.json").read_text(encoding="utf-8")) == {"gameKey": "keep"}
    assert not (cutting / "game.json").exists()


def test_no_index_folder_means_nothing_to_do(tmp_path):
    assert migrate_legacy_vod_games(tmp_path / "none", tmp_path / "games") == []
