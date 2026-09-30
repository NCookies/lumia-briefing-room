import json

import pytest

from lumia_briefing_room.pipeline import game_files as gf


def _write(games, key, **extra):
    folder = games / key
    folder.mkdir(parents=True)
    (folder / "game.json").write_text(json.dumps({"gameKey": key, **extra}), encoding="utf-8")
    return folder


def test_list_is_newest_first_and_skips_broken_or_foreign_folders(tmp_path):
    _write(tmp_path, "20260929_100000")
    _write(tmp_path, "20260930_100000")
    (tmp_path / "20260928_100000").mkdir()
    (tmp_path / "notes").mkdir()
    broken = _write(tmp_path, "20260927_100000")
    (broken / "game.json").write_text("{", encoding="utf-8")

    assert [g["gameKey"] for g in gf.list_games(tmp_path)] == ["20260930_100000", "20260929_100000"]


def test_keys_that_could_escape_the_folder_are_rejected(tmp_path):
    for bad in ("..", "../x", "20260930_100000/../..", "a"):
        with pytest.raises(gf.GameNotFound):
            gf.load_game(tmp_path, bad)


def test_update_game_writes_the_change_atomically(tmp_path):
    _write(tmp_path, "20260930_100000", pinned=False)

    data = gf.update_game(tmp_path, "20260930_100000", lambda d: d.update(pinned=True))

    assert data["pinned"] is True
    assert gf.load_game(tmp_path, "20260930_100000")["pinned"] is True
    assert not list((tmp_path / "20260930_100000").glob("*.tmp"))


def test_update_of_a_missing_game_raises(tmp_path):
    with pytest.raises(gf.GameNotFound):
        gf.update_game(tmp_path, "20260930_100000", lambda d: None)


def test_has_full_video(tmp_path):
    folder = _write(tmp_path, "20260930_100000")
    assert not gf.has_full_video(tmp_path, "20260930_100000")
    (folder / "full.mp4").write_bytes(b"x")
    assert gf.has_full_video(tmp_path, "20260930_100000")
