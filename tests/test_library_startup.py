from pathlib import Path

import pytest

from lumia_briefing_room.config import Config, PathsConfig, resolve_paths
from lumia_briefing_room.pipeline.library_startup import MIGRATION_FAILED, migrate_legacy_layout
from lumia_briefing_room.pipeline.notices import NoticeCenter


@pytest.fixture(autouse=True)
def isolated_local_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))


def _cfg(tmp_path, **kw):
    return Config(paths=PathsConfig(clips=tmp_path / "clips", vod_clips=tmp_path / "vod", temp=tmp_path / "tmp", **kw))


def _seed(tmp_path):
    (tmp_path / "clips" / ".thumbs").mkdir(parents=True)
    (tmp_path / "vod" / ".vods").mkdir(parents=True)
    (tmp_path / "clips" / "a.json").write_text("{}", encoding="utf-8")
    (tmp_path / "clips" / "a.mp4").write_bytes(b"V")
    (tmp_path / "clips" / ".thumbs" / "a.jpg").write_bytes(b"j")
    (tmp_path / "vod" / "vod_x_g01_000001.json").write_text("{}", encoding="utf-8")
    (tmp_path / "vod" / ".vods" / "x.json").write_text("{}", encoding="utf-8")


def test_legacy_layout_info_files_move_to_library_and_videos_stay(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(tmp_path)
    assert migrate_legacy_layout(cfg, NoticeCenter()) == 4
    r = resolve_paths(cfg.paths)
    assert (r.library_steam / "a.json").exists() and (r.library_steam / ".thumbs" / "a.jpg").exists()
    assert (r.library_vod / "vod_x_g01_000001.json").exists() and (r.library_vod / ".vods" / "x.json").exists()
    assert (tmp_path / "clips" / "a.mp4").read_bytes() == b"V"
    assert not (tmp_path / "clips" / "a.json").exists()


def test_second_run_moves_nothing(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(tmp_path)
    migrate_legacy_layout(cfg, NoticeCenter())
    assert migrate_legacy_layout(cfg, NoticeCenter()) == 0


def test_new_layout_has_nothing_to_migrate(tmp_path):
    cfg = Config(paths=PathsConfig(root=tmp_path / "store", temp=tmp_path / "tmp"))
    assert migrate_legacy_layout(cfg, NoticeCenter()) == 0


def test_conflict_is_reported_as_a_notice_and_not_raised(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(tmp_path)
    r = resolve_paths(cfg.paths)
    r.library_steam.mkdir(parents=True)
    (r.library_steam / "a.json").write_text('{"different": true}', encoding="utf-8")
    center = NoticeCenter()
    assert migrate_legacy_layout(cfg, center) == 2, "충돌한 스팀 쪽만 멈추고 영상 파일 쪽은 옮긴다"
    assert [n["kind"] for n in center.list()] == [MIGRATION_FAILED]
    assert (tmp_path / "clips" / "a.json").exists()


def test_missing_clip_folders_are_fine(tmp_path):
    assert migrate_legacy_layout(_cfg(tmp_path), NoticeCenter()) == 0


def test_new_layout_startup_renames_korean_folders(tmp_path):
    root = tmp_path / "store"
    (root / "클립" / "스팀 녹화").mkdir(parents=True)
    (root / "클립" / "스팀 녹화" / "a.mp4").write_bytes(b"V")
    (root / "풀영상" / "스팀 녹화" / "k").mkdir(parents=True)
    cfg = Config(paths=PathsConfig(root=root, temp=tmp_path / "tmp"))
    assert migrate_legacy_layout(cfg, NoticeCenter()) == 0
    assert (root / "clips" / "자동 보관" / "a.mp4").exists() and (root / "full_video" / "steam_replay" / "k").is_dir()
