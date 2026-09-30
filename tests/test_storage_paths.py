from pathlib import Path

import pytest

from lumia_briefing_room import paths as app_paths
from lumia_briefing_room.config import PathsConfig, resolve_paths, suggested_root, uses_legacy_layout


@pytest.fixture(autouse=True)
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.delenv(app_paths.PROFILE_ENV, raising=False)
    return tmp_path


def test_root_splits_into_clip_and_full_video_folders(tmp_path):
    root = tmp_path / "store"
    r = resolve_paths(PathsConfig(root=root))
    assert r.clips_steam == root / "클립" / "스팀 녹화"
    assert r.clips_vod == root / "클립" / "영상 파일"
    assert r.clips_root == root / "클립"
    assert r.games_steam == root / "풀영상" / "스팀 녹화"
    assert r.games_vod == root / "풀영상" / "영상 파일"
    assert not uses_legacy_layout(PathsConfig(root=root))


def test_full_video_location_override_moves_only_full_videos(tmp_path):
    root, big = tmp_path / "store", tmp_path / "hdd" / "full"
    r = resolve_paths(PathsConfig(root=root, full_videos=big))
    assert r.games_steam == big / "스팀 녹화"
    assert r.games_vod == big / "영상 파일"
    assert r.clips_steam == root / "클립" / "스팀 녹화"


def test_info_always_lives_in_app_data_regardless_of_root(tmp_path):
    lib = tmp_path / "local" / "LumiaBriefingRoom" / "library"
    for cfg in (PathsConfig(root=tmp_path / "store"), PathsConfig(clips=tmp_path / "old", vod_clips=tmp_path / "oldvod")):
        r = resolve_paths(cfg)
        assert r.library_steam == lib / "steam"
        assert r.library_vod == lib / "vod"


def test_profile_changes_app_data_folder(tmp_path, monkeypatch):
    monkeypatch.setenv(app_paths.PROFILE_ENV, "dev")
    r = resolve_paths(PathsConfig(root=tmp_path / "store"))
    assert r.library_steam == tmp_path / "local" / "LumiaBriefingRoom-dev" / "library" / "steam"


def test_new_layout_puts_big_temp_files_on_the_video_drive(tmp_path):
    root, big = tmp_path / "store", tmp_path / "hdd" / "full"
    r = resolve_paths(PathsConfig(root=root, full_videos=big))
    assert r.staging_clips == root / ".staging"
    assert r.staging_games == big / ".staging"
    assert r.proxy_cache == root / ".cache" / "proxy"
    assert r.staging_library_steam == r.library_steam / ".staging"


def test_new_layout_full_video_staging_defaults_under_root_full_folder(tmp_path):
    root = tmp_path / "store"
    r = resolve_paths(PathsConfig(root=root))
    assert r.staging_games == root / "풀영상" / ".staging"


def test_legacy_layout_keeps_existing_paths(tmp_path):
    cfg = PathsConfig(clips=tmp_path / "clips", vod_clips=tmp_path / "vod", games=tmp_path / "g")
    r = resolve_paths(cfg)
    assert uses_legacy_layout(cfg)
    assert r.clips_steam == tmp_path / "clips"
    assert r.clips_vod == tmp_path / "vod"
    assert r.games_steam == r.games_vod == tmp_path / "g"
    assert r.staging_clips == tmp_path / "clips" / ".staging"
    assert r.proxy_cache == tmp_path / "clips" / ".proxy"


def test_legacy_layout_games_default_next_to_clips(tmp_path):
    r = resolve_paths(PathsConfig(clips=tmp_path / "x" / "clips"))
    assert r.games_steam == r.games_vod == tmp_path / "x" / "games"


def test_legacy_layout_clips_root_lists_both_roots(tmp_path):
    r = resolve_paths(PathsConfig(clips=tmp_path / "clips", vod_clips=tmp_path / "vod"))
    assert r.clip_roots == (tmp_path / "clips", tmp_path / "vod")


def test_new_layout_has_single_clip_root(tmp_path):
    r = resolve_paths(PathsConfig(root=tmp_path / "s"))
    assert r.clip_roots == (tmp_path / "s" / "클립",)


def test_legacy_layout_vod_staging_stays_next_to_vod_clips(tmp_path):
    r = resolve_paths(PathsConfig(clips=tmp_path / "clips", vod_clips=tmp_path / "vod"))
    assert r.staging_vod_clips == tmp_path / "vod" / ".staging"


def test_new_layout_shares_one_clip_staging(tmp_path):
    r = resolve_paths(PathsConfig(root=tmp_path / "s"))
    assert r.staging_vod_clips == r.staging_clips == tmp_path / "s" / ".staging"


def test_suggested_root_for_fresh_install_is_videos_folder(tmp_path):
    assert suggested_root(PathsConfig()) == tmp_path / "user" / "Videos" / "LumiaBriefingRoom"


def test_suggested_root_is_none_when_user_already_has_old_paths(tmp_path):
    assert suggested_root(PathsConfig(clips=tmp_path / "c")) is None
    assert suggested_root(PathsConfig(games=tmp_path / "g")) is None


def test_suggested_root_is_none_when_default_old_folder_exists(tmp_path):
    (tmp_path / "user" / "Videos" / "LumiaBriefingRoom" / "clips").mkdir(parents=True)
    assert suggested_root(PathsConfig()) is None


def test_existing_root_is_not_suggested_again(tmp_path):
    assert suggested_root(PathsConfig(root=tmp_path / "s")) is None
