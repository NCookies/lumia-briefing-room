import json

import numpy as np

from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.pipeline.game_backfill import backfill_game_results, needs_result

KEY = "20260929_154840"
START = "2026-09-29T15:48:40.330000Z"


def screen(**kw):
    base = dict(
        placement=3, total=None, match_type="normal", match_label="일반", outcome="실험 종료", nickname="나",
        stats={"tk": 13, "kills": 4, "deaths": 2, "assists": 5}, image=np.zeros((9, 16, 3), np.uint8),
    )
    base.update(kw)
    return ResultScreen(**base)


def make_game(games, key=KEY, *, result=None, video=True, mode="battle_royale", **extra):
    folder = games / key
    folder.mkdir(parents=True)
    (folder / "game.json").write_text(json.dumps({
        "gameKey": key, "sessionDir": "s1", "matchStartUtc": START, "gameMode": mode, "matchResult": result, **extra,
    }), encoding="utf-8")
    if video:
        (folder / "full.mp4").write_bytes(b"x")
    return folder


def make_clip(clips, name, **meta):
    clips.mkdir(exist_ok=True)
    (clips / f"{name}.json").write_text(json.dumps({"sessionDir": "s1", "matchStartUtc": START, **meta}), encoding="utf-8")


def read_game(games, key=KEY):
    return json.loads((games / key / "game.json").read_text(encoding="utf-8"))


def test_needs_result_when_missing_unknown_or_placement_unreadable():
    assert needs_result({"matchResult": None})
    assert needs_result({"matchResult": {"matchType": "unknown", "placement": 1}})
    assert needs_result({"matchResult": {"matchType": "normal", "placement": None}})
    assert not needs_result({"matchResult": {"matchType": "normal", "placement": 3}})
    assert not needs_result({"matchResult": {"matchType": "unknown", "placement": 1, "outcome": "승리"}})


def test_fills_a_game_without_result_from_its_full_video_and_saves_the_result_image(tmp_path):
    games, clips = tmp_path / "games", tmp_path / "clips"
    make_game(games)
    seen = []

    report = backfill_game_results(games, clips, find=lambda path: seen.append(path.name) or screen())

    game = read_game(games)
    assert seen == ["full.mp4"] and report.filled == 1
    assert game["matchResult"]["placement"] == 3 and game["matchResult"]["matchType"] == "normal"
    assert game["matchResult"]["imagePath"] == "result.jpg"
    assert (games / KEY / "result.jpg").is_file()


def test_keeps_old_values_where_the_new_read_is_empty(tmp_path):
    games, clips = tmp_path / "games", tmp_path / "clips"
    make_game(games, result={"matchType": "unknown", "matchLabel": "", "placement": 2, "total": 7, "outcome": "실험 종료", "nickname": "나"})

    backfill_game_results(games, clips, find=lambda p: screen(placement=None, outcome=None))

    result = read_game(games)["matchResult"]
    assert (result["placement"], result["total"], result["outcome"], result["matchType"]) == (2, 7, "실험 종료", "normal")


def test_leaves_games_with_a_good_result_unless_forced(tmp_path):
    games, clips = tmp_path / "games", tmp_path / "clips"
    make_game(games, result={"matchType": "rank", "placement": 4})
    calls = []

    backfill_game_results(games, clips, find=lambda p: calls.append(1) or screen())
    assert calls == []

    backfill_game_results(games, clips, find=lambda p: calls.append(1) or screen(), force=True)
    assert calls == [1]


def test_never_touches_a_game_the_user_corrected_by_hand(tmp_path):
    games, clips = tmp_path / "games", tmp_path / "clips"
    make_game(games)
    make_clip(clips, "c1", matchResult={"placement": 5}, matchResultSource="manual")
    calls = []

    report = backfill_game_results(games, clips, find=lambda p: calls.append(1) or screen(), force=True)

    assert calls == [] and report.locked == 1
    assert read_game(games)["matchResult"] is None


def test_skips_games_without_full_video_and_cobalt_games(tmp_path):
    games, clips = tmp_path / "games", tmp_path / "clips"
    make_game(games, "20260929_100000", video=False)
    make_game(games, "20260929_110000", mode="cobalt")
    calls = []

    report = backfill_game_results(games, clips, find=lambda p: calls.append(1) or screen())

    assert calls == [] and report.no_video == 1 and report.skipped == 1


def test_leaves_the_game_alone_when_no_result_screen_is_found_or_reading_fails(tmp_path):
    games, clips = tmp_path / "games", tmp_path / "clips"
    make_game(games, "20260929_100000")
    make_game(games, "20260929_110000")

    def find(path):
        if "110000" in str(path):
            raise RuntimeError("ffmpeg")
        return None

    report = backfill_game_results(games, clips, find=find)

    assert report.not_found == 1 and report.failed == 1 and report.filled == 0
    assert read_game(games, "20260929_100000")["matchResult"] is None


def test_updates_the_saved_clips_of_the_game_too(tmp_path):
    games, clips = tmp_path / "games", tmp_path / "clips"
    make_game(games)
    make_clip(clips, "c1", matchResult=None)
    make_clip(clips, "other", matchResult=None, matchStartUtc="2026-09-29T09:00:00Z")

    backfill_game_results(games, clips, find=lambda p: screen())

    c1 = json.loads((clips / "c1.json").read_text(encoding="utf-8"))
    other = json.loads((clips / "other.json").read_text(encoding="utf-8"))
    assert c1["matchResult"]["placement"] == 3
    assert other["matchResult"] is None
    assert (clips / ".thumbs" / "20260929_154840_result.jpg").is_file()


def test_only_the_named_games_are_read(tmp_path):
    games, clips = tmp_path / "games", tmp_path / "clips"
    make_game(games, "20260929_100000")
    make_game(games, "20260929_110000")
    seen = []

    backfill_game_results(games, clips, find=lambda p: seen.append(p.parent.name) or None, keys=["20260929_110000"])

    assert seen == ["20260929_110000"]
