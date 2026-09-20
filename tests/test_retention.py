import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lumia_briefing_room.config import RetentionConfig
from lumia_briefing_room.pipeline.retention import (
    is_protected,
    purge_expired,
    restore_clip,
    select_for_auto_clean,
    trash_clip,
)

UTC = timezone.utc


def _write_clip(clips_dir: Path, clip_id: str, **meta_overrides) -> Path:
    clips_dir.mkdir(parents=True, exist_ok=True)
    (clips_dir / f"{clip_id}.mp4").write_bytes(b"video")
    thumbs_dir = clips_dir / ".thumbs"
    thumbs_dir.mkdir(exist_ok=True)
    thumb_path = thumbs_dir / f"{clip_id}.jpg"
    thumb_path.write_bytes(b"thumb")

    meta = {
        "title": clip_id,
        "thumbnailPath": str(thumb_path),
        "pinned": False,
        "deletedAt": None,
        "tags": ["kill"],
        **meta_overrides,
    }
    meta_path = clips_dir / f"{clip_id}.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta_path


def _read_meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_trash_clip_moves_mp4_json_and_thumbnail(tmp_path):
    clips_dir = tmp_path / "clips"
    trash_dir = tmp_path / "trash"
    meta_path = _write_clip(clips_dir, "clip1")

    trashed = trash_clip(meta_path, trash_dir)

    assert trashed.exists()
    assert not meta_path.exists()
    assert (trash_dir / "clip1.mp4").exists()
    assert (trash_dir / ".thumbs" / "clip1.jpg").exists()
    assert not (clips_dir / "clip1.mp4").exists()


def test_trash_clip_sets_deleted_at(tmp_path):
    meta_path = _write_clip(tmp_path / "clips", "clip1")
    now = datetime(2026, 1, 1, tzinfo=UTC)

    trashed = trash_clip(meta_path, tmp_path / "trash", now=lambda: now)

    meta = _read_meta(trashed)
    assert meta["deletedAt"] == now.isoformat()


def test_restore_clip_moves_back_and_clears_deleted_at(tmp_path):
    clips_dir = tmp_path / "clips"
    trash_dir = tmp_path / "trash"
    meta_path = _write_clip(clips_dir, "clip1")
    trashed = trash_clip(meta_path, trash_dir, now=lambda: datetime(2026, 1, 1, tzinfo=UTC))

    restored = restore_clip(trashed, clips_dir)

    assert restored.exists()
    assert not trashed.exists()
    assert (clips_dir / "clip1.mp4").exists()
    assert (clips_dir / ".thumbs" / "clip1.jpg").exists()
    meta = _read_meta(restored)
    assert meta["deletedAt"] is None


def test_purge_expired_removes_files_past_trash_days(tmp_path):
    clips_dir = tmp_path / "clips"
    trash_dir = tmp_path / "trash"
    meta_path = _write_clip(clips_dir, "old_clip")
    old_time = datetime(2026, 1, 1, tzinfo=UTC)
    trashed = trash_clip(meta_path, trash_dir, now=lambda: old_time)

    now = old_time + timedelta(days=31)
    purged = purge_expired(trash_dir, trash_days=30, now=lambda: now)

    assert trashed in purged
    assert not trashed.exists()
    assert not (trash_dir / "old_clip.mp4").exists()


def test_purge_expired_keeps_files_within_trash_days(tmp_path):
    clips_dir = tmp_path / "clips"
    trash_dir = tmp_path / "trash"
    meta_path = _write_clip(clips_dir, "recent_clip")
    recent_time = datetime(2026, 1, 1, tzinfo=UTC)
    trashed = trash_clip(meta_path, trash_dir, now=lambda: recent_time)

    now = recent_time + timedelta(days=10)
    purged = purge_expired(trash_dir, trash_days=30, now=lambda: now)

    assert purged == []
    assert trashed.exists()


def test_is_protected_pinned_clip():
    cfg = RetentionConfig(protect_pinned=True)
    assert is_protected({"pinned": True, "tags": []}, cfg) is True


def test_is_protected_by_tag():
    cfg = RetentionConfig(protect_tags=["death"])
    assert is_protected({"pinned": False, "tags": ["death"]}, cfg) is True


def test_is_protected_false_for_ordinary_clip():
    cfg = RetentionConfig(protect_pinned=True, protect_tags=["death"])
    assert is_protected({"pinned": False, "tags": ["kill"]}, cfg) is False


def test_is_protected_pin_protection_can_be_disabled():
    cfg = RetentionConfig(protect_pinned=False)
    assert is_protected({"pinned": True, "tags": []}, cfg) is False


def _meta(clip_id, *, age_days, size_mb=50, pinned=False, tags=("kill",)):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    created = now - timedelta(days=age_days)
    return {
        "_clip_id": clip_id,
        "_created_at": created,
        "_size_bytes": size_mb * 1024 * 1024,
        "pinned": pinned,
        "tags": list(tags),
    }


def test_select_for_auto_clean_by_max_age():
    metas = [_meta("a", age_days=40), _meta("b", age_days=5)]
    cfg = RetentionConfig(auto_clean_enabled=True, max_age_days=30)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    selected = select_for_auto_clean(metas, cfg, now=lambda: now)
    assert [m["_clip_id"] for m in selected] == ["a"]


def test_select_for_auto_clean_respects_protection():
    metas = [_meta("a", age_days=40, pinned=True), _meta("b", age_days=40)]
    cfg = RetentionConfig(auto_clean_enabled=True, max_age_days=30, protect_pinned=True)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    selected = select_for_auto_clean(metas, cfg, now=lambda: now)
    assert [m["_clip_id"] for m in selected] == ["b"]


def test_select_for_auto_clean_by_max_total_gb_picks_oldest_first():
    metas = [
        _meta("oldest", age_days=30, size_mb=600),
        _meta("middle", age_days=20, size_mb=600),
        _meta("newest", age_days=10, size_mb=600),
    ]
    cfg = RetentionConfig(auto_clean_enabled=True, max_total_gb=1.0)  # 1GB = ~1024MB
    now = datetime(2026, 1, 1, tzinfo=UTC)
    selected = select_for_auto_clean(metas, cfg, now=lambda: now)
    # 총 1800MB 중 1024MB 를 넘는 776MB 만큼, 오래된 것부터 제거해야 함
    assert [m["_clip_id"] for m in selected] == ["oldest", "middle"]


def test_select_for_auto_clean_by_max_count():
    metas = [_meta(str(i), age_days=i) for i in range(5)]
    cfg = RetentionConfig(auto_clean_enabled=True, max_count=3)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    selected = select_for_auto_clean(metas, cfg, now=lambda: now)
    assert {m["_clip_id"] for m in selected} == {"3", "4"}


def test_select_for_auto_clean_disabled_returns_nothing():
    metas = [_meta("a", age_days=999)]
    cfg = RetentionConfig(auto_clean_enabled=False, max_age_days=1)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert select_for_auto_clean(metas, cfg, now=lambda: now) == []


def test_select_for_auto_clean_no_limits_set_returns_nothing():
    metas = [_meta("a", age_days=999)]
    cfg = RetentionConfig(auto_clean_enabled=True)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert select_for_auto_clean(metas, cfg, now=lambda: now) == []
