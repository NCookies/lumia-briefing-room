import json
from pathlib import Path

import pytest

from lumia_briefing_room.pipeline import delete_helper
from lumia_briefing_room.pipeline.delete_helper import clip_files, delete_clip, permanently_delete


def _write_clip(clips_dir: Path, clip_id: str, *, thumb=True, proxy=False, **meta) -> Path:
    clips_dir.mkdir(parents=True, exist_ok=True)
    (clips_dir / f"{clip_id}.mp4").write_bytes(b"video")
    data = {"title": clip_id, "thumbnailPath": None, **meta}
    if thumb:
        thumb_path = clips_dir / ".thumbs" / f"{clip_id}.jpg"
        thumb_path.parent.mkdir(exist_ok=True)
        thumb_path.write_bytes(b"thumb")
        data["thumbnailPath"] = str(thumb_path)
    meta_path = clips_dir / f"{clip_id}.json"
    meta_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if proxy:
        proxy_dir = clips_dir / ".proxy"
        proxy_dir.mkdir(exist_ok=True)
        (proxy_dir / f"{clip_id}.mp4").write_bytes(b"proxy")
    return meta_path


def test_clip_files_collects_existing_files_only(tmp_path):
    meta_path = _write_clip(tmp_path, "a", proxy=True)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    files = clip_files(meta_path, meta, proxy=tmp_path / ".proxy" / "a.mp4")

    names = sorted(f.name for f in files)
    assert names == ["a.jpg", "a.json", "a.mp4", "a.mp4"]


def test_clip_files_skips_missing_thumbnail_and_proxy(tmp_path):
    meta_path = _write_clip(tmp_path, "a", thumb=False)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    files = clip_files(meta_path, meta, proxy=tmp_path / ".proxy" / "a.mp4")

    names = sorted(f.name for f in files)
    assert names == ["a.json", "a.mp4"]


def test_permanently_delete_removes_all_given_files(tmp_path):
    meta_path = _write_clip(tmp_path, "a")
    files = clip_files(meta_path, json.loads(meta_path.read_text(encoding="utf-8")))

    permanently_delete(files)

    assert not meta_path.exists()
    assert not (tmp_path / "a.mp4").exists()
    assert not (tmp_path / ".thumbs" / "a.jpg").exists()


def test_send_to_recycle_bin_calls_send2trash_for_each_file(tmp_path, monkeypatch):
    meta_path = _write_clip(tmp_path, "a")
    files = clip_files(meta_path, json.loads(meta_path.read_text(encoding="utf-8")))
    sent = []
    monkeypatch.setattr(delete_helper, "_send2trash", lambda path: sent.append(Path(path)))

    delete_helper.send_to_recycle_bin(files)

    assert sorted(sent) == sorted(files)


def test_delete_clip_permanent_mode_removes_files(tmp_path):
    meta_path = _write_clip(tmp_path, "a")

    delete_clip(meta_path, mode="permanent")

    assert not meta_path.exists() and not (tmp_path / "a.mp4").exists()


def test_delete_clip_recycle_mode_uses_recycle_bin(tmp_path, monkeypatch):
    meta_path = _write_clip(tmp_path, "a")
    sent = []
    monkeypatch.setattr(delete_helper, "_send2trash", lambda path: sent.append(Path(path)))

    delete_clip(meta_path, mode="recycle")

    assert len(sent) == 3  # json, mp4, thumbnail


def test_delete_clip_archives_label_before_removing(tmp_path):
    meta_path = _write_clip(tmp_path, "a", userLabel="pvp")
    archive_dir = tmp_path / ".labels"

    delete_clip(meta_path, mode="permanent", archive_dir=archive_dir)

    assert (archive_dir / "a.json").exists()


def test_delete_clip_records_game_before_removing(tmp_path):
    meta_path = _write_clip(
        tmp_path, "a", matchStartUtc="2026-01-01T00:00:00Z", sessionDir="s1", matchResult={"placement": 1},
    )
    records_dir = tmp_path / ".games"

    delete_clip(meta_path, mode="permanent", records_dir=records_dir)

    assert list(records_dir.glob("*.json"))


def test_delete_clip_removes_proxy_file_when_given(tmp_path):
    meta_path = _write_clip(tmp_path, "a", proxy=True)
    proxy = tmp_path / ".proxy" / "a.mp4"

    delete_clip(meta_path, mode="permanent", proxy=proxy)

    assert not proxy.exists()


def test_unknown_mode_falls_back_to_recycle(tmp_path, monkeypatch):
    meta_path = _write_clip(tmp_path, "a")
    sent = []
    monkeypatch.setattr(delete_helper, "_send2trash", lambda path: sent.append(Path(path)))

    delete_clip(meta_path, mode="not-a-real-mode")

    assert len(sent) > 0
