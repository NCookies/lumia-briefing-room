import pytest

from lumia_briefing_room.config import PathsConfig
from lumia_briefing_room.pipeline.folder_names import migrate_folder_names


def touch(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_korean_folders_are_renamed_and_auto_clips_move_to_auto_archive(tmp_path):
    root = tmp_path / "store"
    touch(root / "클립" / "스팀 녹화" / "a.mp4", b"A")
    touch(root / "클립" / "스팀 녹화" / "sub" / "b.mp4", b"B")
    touch(root / "클립" / "영상 파일" / "v.mp4", b"V")
    touch(root / "클립" / "아야" / "c.mp4", b"C")
    touch(root / "풀영상" / "스팀 녹화" / "20260928_160025" / "full.mp4", b"F")
    touch(root / "풀영상" / "영상 파일" / "vod_x_g01" / "game.json", b"{}")

    assert migrate_folder_names(PathsConfig(root=root)) > 0

    assert (root / "clips" / "자동 보관" / "a.mp4").read_bytes() == b"A"
    assert (root / "clips" / "자동 보관" / "sub" / "b.mp4").read_bytes() == b"B"
    assert (root / "clips" / "자동 보관" / "v.mp4").read_bytes() == b"V"
    assert (root / "clips" / "아야" / "c.mp4").read_bytes() == b"C", "사용자가 만든 폴더는 그대로 카테고리"
    assert (root / "full_video" / "steam_replay" / "20260928_160025" / "full.mp4").read_bytes() == b"F"
    assert (root / "full_video" / "vod" / "vod_x_g01" / "game.json").exists()
    for old in ("클립", "풀영상"):
        assert not (root / old).exists()
    assert not (root / "clips" / "스팀 녹화").exists() and not (root / "clips" / "영상 파일").exists()


def test_running_twice_changes_nothing(tmp_path):
    root = tmp_path / "store"
    touch(root / "클립" / "스팀 녹화" / "a.mp4")
    cfg = PathsConfig(root=root)
    assert migrate_folder_names(cfg) > 0
    assert migrate_folder_names(cfg) == 0


def test_legacy_layout_and_missing_root_are_left_alone(tmp_path):
    touch(tmp_path / "클립" / "스팀 녹화" / "a.mp4")
    assert migrate_folder_names(PathsConfig()) == 0
    assert (tmp_path / "클립" / "스팀 녹화" / "a.mp4").exists()
    assert migrate_folder_names(PathsConfig(root=tmp_path / "nothing")) == 0


def test_custom_full_video_folder_subfolders_are_renamed(tmp_path):
    root, big = tmp_path / "store", tmp_path / "big"
    touch(big / "스팀 녹화" / "20260928_160025" / "full.mp4")
    touch(big / "영상 파일" / "vod_x_g01" / "full.mp4")
    migrate_folder_names(PathsConfig(root=root, full_videos=big))
    assert (big / "steam_replay" / "20260928_160025" / "full.mp4").exists()
    assert (big / "vod" / "vod_x_g01" / "full.mp4").exists()


def test_name_clashes_merge_without_overwriting(tmp_path):
    root = tmp_path / "store"
    touch(root / "클립" / "스팀 녹화" / "a.mp4", b"OLD")
    touch(root / "clips" / "자동 보관" / "a.mp4", b"NEW")
    touch(root / "클립" / "아야" / "x.mp4", b"X")
    touch(root / "clips" / "아야" / "y.mp4", b"Y")
    migrate_folder_names(PathsConfig(root=root))
    assert (root / "clips" / "자동 보관" / "a.mp4").read_bytes() == b"NEW"
    assert sorted(p.name for p in (root / "clips" / "자동 보관").iterdir()) == ["a (2).mp4", "a.mp4"]
    assert (root / "clips" / "아야" / "x.mp4").exists() and (root / "clips" / "아야" / "y.mp4").exists()


def test_a_failure_on_one_folder_does_not_stop_the_others(tmp_path, monkeypatch):
    root = tmp_path / "store"
    touch(root / "클립" / "스팀 녹화" / "a.mp4")
    touch(root / "풀영상" / "스팀 녹화" / "k" / "full.mp4")
    import os as _os
    real = _os.replace

    def flaky(src, dst):
        if "클립" in str(src) and str(src).endswith("클립"):
            raise PermissionError("locked")
        return real(src, dst)

    monkeypatch.setattr("lumia_briefing_room.pipeline.folder_names.os.replace", flaky)
    migrate_folder_names(PathsConfig(root=root))
    assert (root / "full_video" / "steam_replay" / "k" / "full.mp4").exists()
