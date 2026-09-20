import json
from pathlib import Path

from lumia_briefing_room.api.clips import find_clip, scan_clips, to_summary_dict


def _write_clip(clips_dir: Path, clip_id: str, **meta_overrides) -> None:
    clips_dir.mkdir(parents=True, exist_ok=True)
    (clips_dir / f"{clip_id}.mp4").write_bytes(b"x" * 100)
    meta = {"title": clip_id, "tags": ["kill"], "pinned": False, "deletedAt": None, **meta_overrides}
    (clips_dir / f"{clip_id}.json").write_text(json.dumps(meta), encoding="utf-8")


def test_scan_clips_finds_all_json_files(tmp_path):
    _write_clip(tmp_path, "a")
    _write_clip(tmp_path, "b")
    clips = scan_clips(tmp_path)
    assert {c.id for c in clips} == {"a", "b"}


def test_scan_clips_empty_directory(tmp_path):
    assert scan_clips(tmp_path) == []


def test_scan_clips_missing_directory(tmp_path):
    assert scan_clips(tmp_path / "does_not_exist") == []


def test_scan_clips_ignores_non_json_files(tmp_path):
    _write_clip(tmp_path, "a")
    (tmp_path / "readme.txt").write_text("hi", encoding="utf-8")
    clips = scan_clips(tmp_path)
    assert {c.id for c in clips} == {"a"}

def test_scan_clips_skips_trash_and_thumbs_subdirectories(tmp_path):
    _write_clip(tmp_path, "a")
    _write_clip(tmp_path / ".trash", "trashed")
    (tmp_path / ".thumbs").mkdir()
    clips = scan_clips(tmp_path)
    assert {c.id for c in clips} == {"a"}


def test_clip_summary_has_size_and_meta(tmp_path):
    _write_clip(tmp_path, "a", title="테스트 클립")
    (clip,) = scan_clips(tmp_path)
    assert clip.size_bytes == 100
    assert clip.meta["title"] == "테스트 클립"
    assert clip.created_at is not None


def test_find_clip_returns_matching_id(tmp_path):
    _write_clip(tmp_path, "a")
    _write_clip(tmp_path, "b")
    found = find_clip(tmp_path, "b")
    assert found is not None
    assert found.id == "b"


def test_find_clip_returns_none_when_missing(tmp_path):
    _write_clip(tmp_path, "a")
    assert find_clip(tmp_path, "nonexistent") is None


def test_to_summary_dict_fills_retention_keys(tmp_path):
    _write_clip(tmp_path, "a")
    (clip,) = scan_clips(tmp_path)
    d = to_summary_dict(clip)
    assert d["_size_bytes"] == 100
    assert d["_created_at"] == clip.created_at
    assert d["title"] == "a"
