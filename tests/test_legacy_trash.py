import json
from pathlib import Path

from lumia_briefing_room.pipeline import legacy_trash
from lumia_briefing_room.pipeline.legacy_trash import count_legacy_trash, recycle_legacy_trash, restore_legacy_trash


def _write_clip(directory: Path, clip_id: str, *, thumb=True, **meta) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{clip_id}.mp4").write_bytes(b"video")
    data = {"title": clip_id, "thumbnailPath": None, "deletedAt": "2026-01-01T00:00:00Z", **meta}
    if thumb:
        thumb_path = directory / ".thumbs" / f"{clip_id}.jpg"
        thumb_path.parent.mkdir(exist_ok=True)
        thumb_path.write_bytes(b"thumb")
        data["thumbnailPath"] = str(thumb_path)
    meta_path = directory / f"{clip_id}.json"
    meta_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return meta_path


def test_count_legacy_trash_counts_json_files_across_roots(tmp_path):
    _write_clip(tmp_path / "steam" / ".trash", "a")
    _write_clip(tmp_path / "steam" / ".trash", "b")
    _write_clip(tmp_path / "vod" / ".trash", "c")

    assert count_legacy_trash(tmp_path / "steam", tmp_path / "vod") == 3


def test_count_legacy_trash_is_zero_when_folder_is_empty_or_missing(tmp_path):
    assert count_legacy_trash(tmp_path / "steam") == 0
    (tmp_path / "steam" / ".trash").mkdir(parents=True)
    assert count_legacy_trash(tmp_path / "steam") == 0


def test_restore_legacy_trash_moves_clips_back_and_clears_deleted_at(tmp_path):
    root = tmp_path / "clips"
    _write_clip(root / ".trash", "a")

    moved = restore_legacy_trash(root)

    assert moved == 1
    assert (root / "a.json").exists()
    assert (root / "a.mp4").exists()
    assert (root / ".thumbs" / "a.jpg").exists()
    meta = json.loads((root / "a.json").read_text(encoding="utf-8"))
    assert "deletedAt" not in meta
    assert not (root / ".trash" / "a.json").exists()


def test_recycle_legacy_trash_sends_files_to_recycle_bin(tmp_path, monkeypatch):
    root = tmp_path / "clips"
    _write_clip(root / ".trash", "a", userLabel="pvp")
    sent = []
    monkeypatch.setattr(legacy_trash, "delete_clip", lambda meta_path, **kw: sent.append((meta_path, kw)))

    moved = recycle_legacy_trash(root)

    assert moved == 1
    assert sent[0][1]["mode"] == "recycle"
