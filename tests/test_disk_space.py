import json

from lumia_briefing_room.pipeline import disk_space as ds

GB = 2**30


def test_expected_game_size_without_history_uses_the_bitrate_default():
    assert ds.expected_game_bytes([]) == int(ds.DEFAULT_MB_PER_MIN * ds.DEFAULT_GAME_MINUTES * 2**20)


def test_expected_game_size_is_the_mean_of_the_recent_sizes():
    sizes = [1 * GB, 2 * GB, 3 * GB]
    assert ds.expected_game_bytes(sizes) == 2 * GB


def test_only_the_latest_sizes_count():
    sizes = [100 * GB] + [2 * GB] * ds.RECENT_GAMES
    assert ds.expected_game_bytes(sizes) == 2 * GB


def test_low_when_free_is_under_five_games_and_the_configured_floor():
    status = ds.evaluate(free_bytes=10 * GB, expected_bytes=3 * GB, min_free_gb=0)
    assert status.low and status.threshold_bytes == 15 * GB


def test_the_configured_floor_raises_the_threshold():
    status = ds.evaluate(free_bytes=19 * GB, expected_bytes=1 * GB, min_free_gb=20)
    assert status.low and status.threshold_bytes == 20 * GB


def test_plenty_of_space_is_ok_and_has_no_message():
    status = ds.evaluate(free_bytes=100 * GB, expected_bytes=3 * GB, min_free_gb=20)
    assert not status.low and status.message is None


def test_low_message_names_the_free_space_and_the_remedies():
    status = ds.evaluate(free_bytes=int(12.3 * GB), expected_bytes=3 * GB, min_free_gb=20)
    assert "12.3GB" in status.message
    assert "풀영상" in status.message and "저장한 클립" in status.message
    assert "자동 정리를 켜거나" in status.message
    assert "한도를 낮추" not in status.message


def test_recent_full_video_sizes_come_from_game_json_newest_last(tmp_path):
    for key, size in (("20260929_100000", 3 * GB), ("20260930_100000", 4 * GB), ("20260928_100000", 2 * GB)):
        d = tmp_path / key
        d.mkdir()
        (d / "game.json").write_text(json.dumps({"fullVideo": {"sizeBytes": size}}), encoding="utf-8")
    (tmp_path / "20260927_100000").mkdir()
    (tmp_path / "20260926_100000").mkdir()
    (tmp_path / "20260926_100000" / "game.json").write_text(json.dumps({"fullVideo": None}), encoding="utf-8")
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "game.json").write_text("{", encoding="utf-8")

    assert ds.recent_full_video_sizes(tmp_path) == [2 * GB, 3 * GB, 4 * GB]


def test_recent_sizes_of_a_missing_folder_is_empty(tmp_path):
    assert ds.recent_full_video_sizes(tmp_path / "nope") == []
