import json
from pathlib import Path

from lumia_briefing_room.api import clips as clips_api
from lumia_briefing_room.api.clips import find_clip, find_clips, scan_clips, to_summary_dict


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


def test_scan_skips_files_that_vanish_or_are_unreadable_while_scanning(tmp_path, monkeypatch):
    import json as _json

    from lumia_briefing_room.api import clips as clips_module

    (tmp_path / "ok.json").write_text(_json.dumps({"title": "ok"}), encoding="utf-8")
    (tmp_path / "gone.json").write_text(_json.dumps({"title": "gone"}), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    original = clips_module._summary

    def flaky(path, *args):
        if path.stem == "gone":
            raise FileNotFoundError(path)
        return original(path, *args)

    monkeypatch.setattr(clips_module, "_summary", flaky)

    assert [c.id for c in clips_module.scan_clips(tmp_path)] == ["ok"]


def test_find_clips_matches_find_clip_for_each_id_and_skips_missing(tmp_path):
    _write_clip(tmp_path, "a")
    _write_clip(tmp_path, "b")
    found = find_clips(tmp_path, ["a", "b", "nonexistent"])
    assert set(found) == {"a", "b"}
    for clip_id, clip in found.items():
        assert clip == find_clip(tmp_path, clip_id)


def test_find_clips_links_videos_once_no_matter_how_many_clips(tmp_path, monkeypatch):
    for clip_id in "abcde":
        _write_clip(tmp_path, clip_id)
    calls = []
    real = clips_api.link_all
    monkeypatch.setattr(clips_api, "link_all", lambda *a, **kw: (calls.append(1), real(*a, **kw))[1])
    assert len(find_clips(tmp_path, list("abcde"))) == 5
    assert len(calls) == 1


def test_find_clips_finds_a_clip_whose_video_was_moved_by_its_tag(tmp_path, monkeypatch):
    from lumia_briefing_room.pipeline import clip_files

    library, elsewhere = tmp_path / "lib", tmp_path / "moved"
    _write_clip(library, "a", clipUid="uid-a")
    (library / "a.mp4").unlink()
    elsewhere.mkdir()
    (elsewhere / "renamed.mp4").write_bytes(b"x" * 100)
    monkeypatch.setattr(clip_files, "read_clip_uid", lambda p: "uid-a" if p.name == "renamed.mp4" else None)
    assert find_clips(library, ["a"], [elsewhere])["a"].video == elsewhere / "renamed.mp4"
