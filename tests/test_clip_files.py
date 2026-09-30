from pathlib import Path

import pytest

from lumia_briefing_room.api.clips import find_clip, scan_clips
from lumia_briefing_room.pipeline import clip_files as cf


def _meta(d: Path, cid: str, **extra):
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{cid}.json").write_text('{"title":"t"}', encoding="utf-8")


def test_find_video_beside_meta_first(tmp_path):
    meta, root = tmp_path / "lib", tmp_path / "clips"
    _meta(meta, "a")
    (meta / "a.mp4").write_bytes(b"1")
    (root / "x").mkdir(parents=True)
    (root / "x" / "a.mp4").write_bytes(b"2")
    assert cf.find_video(meta, "a", [root]) == meta / "a.mp4"


def test_find_video_recurses_into_subfolders(tmp_path):
    meta, root = tmp_path / "lib", tmp_path / "clips"
    (root / "캐릭터" / "아야").mkdir(parents=True)
    (root / "캐릭터" / "아야" / "a.mp4").write_bytes(b"x")
    assert cf.find_video(meta, "a", [root]) == root / "캐릭터" / "아야" / "a.mp4"
    assert cf.find_video(meta, "missing", [root]) is None


def test_hidden_folders_and_temp_files_are_not_clips(tmp_path):
    root = tmp_path / "clips"
    for rel in (".staging/job/a.mp4", ".cache/proxy/b.mp4", "c.replace.mp4", "d.trim.mp4", "e.mp4.part", "f.tmp.mp4", "ok.mp4"):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    assert [p.name for p in cf.walk_videos([root])] == ["ok.mp4"]


def test_missing_root_is_skipped_not_an_error(tmp_path):
    assert list(cf.walk_videos([tmp_path / "no_such_drive"])) == []


def test_scan_clips_reads_video_from_clip_roots(tmp_path):
    meta, root = tmp_path / "lib", tmp_path / "clips"
    _meta(meta, "a")
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "a.mp4").write_bytes(b"12345")
    (clip,) = scan_clips(meta, [root])
    assert clip.video == root / "sub" / "a.mp4" and clip.size_bytes == 5
    assert find_clip(meta, "a", [root]).video == root / "sub" / "a.mp4"


def test_scan_clips_without_roots_keeps_old_beside_behaviour(tmp_path):
    _meta(tmp_path, "a")
    (tmp_path / "a.mp4").write_bytes(b"123")
    (clip,) = scan_clips(tmp_path)
    assert clip.size_bytes == 3


def _staged(staging: Path):
    (staging / ".thumbs").mkdir(parents=True)
    (staging / "a.mp4").write_bytes(b"VID")
    (staging / ".thumbs" / "a.jpg").write_bytes(b"jpg")
    (staging / "a.json").write_text("{}", encoding="utf-8")


def test_commit_staged_clips_splits_video_and_info(tmp_path):
    staging, meta, video = tmp_path / "st", tmp_path / "lib", tmp_path / "clips"
    _staged(staging)
    moved = cf.commit_staged_clips(staging, meta, video)
    assert (video / "a.mp4").read_bytes() == b"VID" and not (meta / "a.mp4").exists()
    assert (meta / "a.json").exists() and (meta / ".thumbs" / "a.jpg").exists()
    assert moved == [meta / "a.json"]
    assert not staging.exists()


def test_commit_staged_clips_moves_video_before_json(tmp_path, monkeypatch):
    staging, meta, video = tmp_path / "st", tmp_path / "lib", tmp_path / "clips"
    _staged(staging)
    order = []
    real = cf.move_file
    monkeypatch.setattr(cf, "move_file", lambda s, d: (order.append(Path(d).suffix), real(s, d))[1])
    cf.commit_staged_clips(staging, meta, video)
    assert order == [".mp4", ".jpg", ".json"]


def test_move_file_across_devices_uses_part_name_then_renames(tmp_path, monkeypatch):
    src, dst = tmp_path / "a.mp4", tmp_path / "out" / "a.mp4"
    src.write_bytes(b"data")
    seen = {}
    real_replace = cf.os.replace

    def replace(a, b):
        if Path(a) == src:
            raise OSError(18, "cross-device")
        seen["part"] = Path(a).name
        return real_replace(a, b)

    monkeypatch.setattr(cf.os, "replace", replace)
    cf.move_file(src, dst)
    assert dst.read_bytes() == b"data" and not src.exists()
    assert seen["part"] == "a.mp4.part"


def test_move_file_refuses_to_overwrite_existing_destination(tmp_path):
    src, dst = tmp_path / "a.mp4", tmp_path / "b" / "a.mp4"
    dst.parent.mkdir()
    src.write_bytes(b"new")
    dst.write_bytes(b"old")
    with pytest.raises(FileExistsError):
        cf.move_file(src, dst, overwrite=False)
    assert dst.read_bytes() == b"old" and src.exists()
