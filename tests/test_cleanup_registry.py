import time

from lumia_briefing_room.config import RetentionConfig
from lumia_briefing_room.pipeline.cleanup_registry import CleanupPreviewRegistry


def _wait_until(predicate, *, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for condition")


def _write_clip(clips_dir, clip_id, *, days_ago, size=1000):
    import json
    from datetime import datetime, timedelta, timezone

    clips_dir.mkdir(parents=True, exist_ok=True)
    (clips_dir / f"{clip_id}.mp4").write_bytes(b"x" * size)
    match_start = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")
    (clips_dir / f"{clip_id}.json").write_text(
        json.dumps({"matchStartUtc": match_start, "tags": [], "pinned": False}), encoding="utf-8"
    )


def test_notify_debounces_and_recomputes_once(tmp_path):
    clips = tmp_path / "clips"
    _write_clip(clips, "old", days_ago=40)
    cfg = RetentionConfig(auto_clean_enabled=True, max_age_days=30)
    registry = CleanupPreviewRegistry(debounce_sec=0.05)
    registry.configure(lambda: (clips, cfg))

    assert registry.snapshot() == {}
    registry.notify_clips_changed()
    registry.notify_clips_changed()  # 연달아 불러도 마지막 한 번만 계산돼야 한다
    _wait_until(lambda: registry.snapshot() != {})

    assert set(registry.snapshot()) == {"old"}


def test_recompute_now_is_immediate(tmp_path):
    clips = tmp_path / "clips"
    _write_clip(clips, "old", days_ago=40)
    cfg = RetentionConfig(auto_clean_enabled=True, max_age_days=30)
    registry = CleanupPreviewRegistry(debounce_sec=10.0)
    registry.configure(lambda: (clips, cfg))

    registry.recompute_now()

    assert set(registry.snapshot()) == {"old"}


def test_snapshot_before_configure_is_empty():
    registry = CleanupPreviewRegistry(debounce_sec=0.01)
    assert registry.snapshot() == {}
