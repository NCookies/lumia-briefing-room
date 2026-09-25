import json
from datetime import datetime, timedelta, timezone

from lumia_briefing_room.config import RetentionConfig
from lumia_briefing_room.pipeline.cleanup import run_cleanup
from lumia_briefing_room.pipeline.label_archive import archive_dir_for, archive_if_labeled, load_archived
from lumia_briefing_room.pipeline.retention import purge_expired

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def write_clip(root, clip_id, *, label="pvp", deleted_days_ago=None, **meta):
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{clip_id}.mp4").write_bytes(b"x" * 100)
    thumb = root / ".thumbs" / f"{clip_id}.jpg"
    thumb.parent.mkdir(exist_ok=True)
    thumb.write_bytes(b"jpg")
    deleted = None
    if deleted_days_ago is not None:
        deleted = (NOW - timedelta(days=deleted_days_ago)).isoformat()
    data = {
        "title": clip_id, "tags": ["kill"], "pinned": False, "deletedAt": deleted, "userLabel": label,
        "labelSource": "user", "pvpScore": 1.0, "pvpSignals": ["kill_delta"], "killDelta": 1,
        "enemyRingMean": 0.4, "gameDay": 3, "matchStartUtc": (NOW - timedelta(days=30)).isoformat(),
        "thumbnailPath": str(thumb), "matchResult": {"placement": 2, "imagePath": "C:/x/result.jpg"}, **meta,
    }
    (root / f"{clip_id}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return root / f"{clip_id}.json"


def test_labeled_clip_keeps_its_evidence_and_label_without_paths_or_video(tmp_path):
    meta_path = write_clip(tmp_path / "clips", "a_01")
    archive = archive_dir_for(tmp_path / "clips")

    archive_if_labeled(meta_path, archive)

    kept = json.loads((archive / "a_01.json").read_text(encoding="utf-8"))
    assert kept["userLabel"] == "pvp" and kept["pvpSignals"] == ["kill_delta"] and kept["enemyRingMean"] == 0.4
    assert kept["id"] == "a_01" and kept["archivedAt"]
    assert "thumbnailPath" not in kept and "imagePath" not in kept["matchResult"] and kept["matchResult"]["placement"] == 2
    assert not list(archive.glob("*.mp4"))


def test_unlabeled_clip_is_not_archived(tmp_path):
    meta_path = write_clip(tmp_path / "clips", "a_01", label=None)
    archive = archive_dir_for(tmp_path / "clips")

    assert archive_if_labeled(meta_path, archive) is None
    assert not archive.exists()


def test_purging_an_expired_trash_clip_archives_only_the_labeled_ones(tmp_path):
    clips = tmp_path / "clips"
    trash = clips / ".trash"
    write_clip(trash, "keep", deleted_days_ago=40)
    write_clip(trash, "drop", label=None, deleted_days_ago=40)

    purge_expired(trash, trash_days=30, now=lambda: NOW, archive_dir=archive_dir_for(clips))

    assert not (trash / "keep.json").exists() and not (trash / "keep.mp4").exists()
    assert [m["id"] for m in load_archived(clips)] == ["keep"]


def test_permanent_auto_delete_archives_labeled_clips(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "keep")
    write_clip(clips, "drop", label=None)
    cfg = RetentionConfig(delete_mode="permanent", auto_clean_enabled=True, max_age_days=1, protect_pinned=False, protect_tags=[])

    run_cleanup(clips, clips / ".trash", cfg, now=NOW)

    assert not (clips / "keep.mp4").exists()
    assert [m["id"] for m in load_archived(clips)] == ["keep"]


def test_load_archived_is_empty_without_an_archive(tmp_path):
    assert load_archived(tmp_path) == []


def test_archive_keeps_the_clip_uid_and_invents_one_for_clips_without(tmp_path):
    root = tmp_path / "clips"
    with_uid = write_clip(root, "a_01", clipUid="u" * 32)
    without = write_clip(root, "a_02")
    archive = archive_dir_for(root)

    archive_if_labeled(with_uid, archive)
    archive_if_labeled(without, archive)

    assert json.loads((archive / "a_01.json").read_text(encoding="utf-8"))["clipUid"] == "u" * 32
    invented = json.loads((archive / "a_02.json").read_text(encoding="utf-8"))["clipUid"]
    assert len(invented) == 32
