import json
import threading
from datetime import datetime, timedelta, timezone

from lumia_briefing_room.config import RetentionConfig
from lumia_briefing_room.pipeline.cleanup import cleanup_loop, cleanup_preview, plan_cleanup, run_cleanup

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def write_clip(root, clip_id, *, days_ago=0, size=6000, thumb=True, **meta):
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{clip_id}.mp4").write_bytes(b"x" * size)
    data = {
        "title": clip_id, "tags": ["kill"], "pinned": False,
        "matchStartUtc": iso(days_ago), "thumbnailPath": None, **meta,
    }
    if thumb:
        thumb_path = root / ".thumbs" / f"{clip_id}.jpg"
        thumb_path.parent.mkdir(exist_ok=True)
        thumb_path.write_bytes(b"jpg")
        data["thumbnailPath"] = str(thumb_path)
    (root / f"{clip_id}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def cfg(**kw):
    return RetentionConfig(auto_clean_enabled=True, **kw)


def names(paths):
    return sorted(p.stem for p in paths)


def test_disabled_cleanup_plans_nothing(tmp_path):
    write_clip(tmp_path / "clips", "old", days_ago=400)

    plan = plan_cleanup(tmp_path / "clips", RetentionConfig(auto_clean_enabled=False, max_age_days=1), now=NOW)

    assert plan.to_delete == []


def test_max_age_deletes_old_unprotected_clips_permanently_by_default(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "old", days_ago=40)
    write_clip(clips, "fresh", days_ago=2)
    write_clip(clips, "pinned_old", days_ago=40, pinned=True)
    write_clip(clips, "death_old", days_ago=40, tags=["death"])

    plan = run_cleanup(clips, cfg(max_age_days=30, protect_tags=["death"]), now=NOW)

    assert names(plan.to_delete) == ["old"]
    assert not (clips / "old.json").exists() and not (clips / "old.mp4").exists()
    assert (clips / "fresh.json").exists() and (clips / "pinned_old.json").exists()
    assert (clips / "death_old.json").exists()


def test_recycle_mode_sends_files_to_the_recycle_bin_instead_of_deleting(tmp_path, monkeypatch):
    import lumia_briefing_room.pipeline.delete_helper as delete_helper

    clips = tmp_path / "clips"
    write_clip(clips, "old", days_ago=40)
    sent = []
    monkeypatch.setattr(delete_helper, "_send2trash", lambda path: sent.append(path))

    run_cleanup(clips, cfg(max_age_days=30, delete_mode="recycle"), now=NOW)

    # 실제로 지우는 대신 재활용(Send2Trash) 함수가 클립의 파일마다 불렸다
    from pathlib import Path

    assert {Path(p).name for p in sent} == {"old.json", "old.mp4", "old.jpg"}


def test_by_default_only_pinned_clips_are_protected(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "old", days_ago=40)
    write_clip(clips, "pinned_old", days_ago=40, pinned=True)
    write_clip(clips, "death_old", days_ago=40, tags=["death"])

    plan = run_cleanup(clips, cfg(max_age_days=30), now=NOW)

    assert names(plan.to_delete) == ["death_old", "old"]
    assert (clips / "pinned_old.json").exists()


def test_max_count_keeps_the_newest(tmp_path):
    clips = tmp_path / "clips"
    for i, days in enumerate([5, 4, 3, 2, 1]):
        write_clip(clips, f"c{i}", days_ago=days)

    plan = plan_cleanup(clips, cfg(max_count=2), now=NOW)

    assert names(plan.to_delete) == ["c0", "c1", "c2"]


def test_max_total_gb_frees_oldest_until_under_the_limit(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "a", days_ago=3, size=6000)
    write_clip(clips, "b", days_ago=2, size=6000)
    write_clip(clips, "c", days_ago=1, size=6000)

    plan = plan_cleanup(clips, cfg(max_total_gb=13000 / 1024**3), now=NOW)

    assert names(plan.to_delete) == ["a"]
    assert plan.bytes_to_free == 6000


def test_age_uses_game_time_not_file_modification_time(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "old_but_just_edited", days_ago=90)

    plan = plan_cleanup(clips, cfg(max_age_days=30), now=NOW)

    assert names(plan.to_delete) == ["old_but_just_edited"]


def test_dry_run_plans_without_touching_files(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "old", days_ago=40)

    plan = plan_cleanup(clips, cfg(max_age_days=30), now=NOW)

    assert names(plan.to_delete) == ["old"]
    assert (clips / "old.json").exists()


def test_orphan_result_images_are_removed_but_referenced_ones_stay(tmp_path):
    clips = tmp_path / "clips"
    kept_image = clips / ".thumbs" / "20260920_100000_result.jpg"
    orphan = clips / ".thumbs" / "20260919_100000_result.jpg"
    kept_image.parent.mkdir(parents=True)
    kept_image.write_bytes(b"j")
    orphan.write_bytes(b"j")
    write_clip(clips, "a", days_ago=1, matchResult={"imagePath": str(kept_image)})

    run_cleanup(clips, cfg(), now=NOW)

    assert kept_image.exists() and not orphan.exists()


def test_cleanup_loop_runs_immediately_and_every_interval_until_stopped():
    stop = threading.Event()
    runs = []

    def run():
        runs.append(1)
        if len(runs) == 3:
            stop.set()

    cleanup_loop(run, stop, interval_sec=0.01)

    assert len(runs) == 3


def test_cleanup_loop_survives_a_failing_run():
    stop = threading.Event()
    calls = []

    def run():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        stop.set()

    cleanup_loop(run, stop, interval_sec=0.01)

    assert len(calls) == 2


def test_make_cleanup_runner_reads_the_current_config_file_each_time(tmp_path):
    import json

    from lumia_briefing_room.config import Config, PathsConfig, save_config
    from lumia_briefing_room.pipeline.cleanup import make_cleanup_runner

    clips = tmp_path / "clips"
    game = tmp_path / "games" / "20200101_000000"
    game.mkdir(parents=True)
    (game / "full.mp4").write_bytes(b"x" * 100)
    (game / "game.json").write_text(json.dumps({"matchStartUtc": "2020-01-01T00:00:00Z", "candidates": []}), encoding="utf-8")
    config_path = tmp_path / "config.json"
    off = RetentionConfig(auto_clean_enabled=False, max_age_days=30)
    save_config(Config(paths=PathsConfig(clips=clips), retention=off), config_path)
    runner = make_cleanup_runner(config_path)

    assert runner().to_delete == []

    on = RetentionConfig(auto_clean_enabled=True, max_age_days=30)
    save_config(Config(paths=PathsConfig(clips=clips), retention=on), config_path)
    plan = runner()

    assert names(plan.to_delete) == ["20200101_000000"]
    assert not (game / "full.mp4").exists()
    assert (game / "game.json").exists()


def test_cleanup_preview_tags_age_reason_with_due_date(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "old", days_ago=40)
    write_clip(clips, "fresh", days_ago=2)

    preview = cleanup_preview(clips, cfg(max_age_days=30), now=NOW)

    assert set(preview) == {"old"}
    assert preview["old"]["reason"] == "age"
    assert preview["old"]["dueAt"] == iso(10)  # matchStartUtc(40일 전) + 30일 = 10일 전


def test_cleanup_preview_count_and_size_reasons_have_no_due_date(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "a", days_ago=3)
    write_clip(clips, "b", days_ago=2)
    write_clip(clips, "c", days_ago=1)

    preview = cleanup_preview(clips, cfg(max_count=2), now=NOW)

    assert set(preview) == {"a"}
    assert preview["a"]["reason"] == "count"
    assert preview["a"]["dueAt"] is None


def test_cleanup_preview_disabled_returns_empty(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "old", days_ago=400)

    preview = cleanup_preview(clips, RetentionConfig(auto_clean_enabled=False, max_age_days=1), now=NOW)

    assert preview == {}


def test_cleanup_preview_protected_clips_are_not_listed(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "old_pinned", days_ago=40, pinned=True)

    preview = cleanup_preview(clips, cfg(max_age_days=30), now=NOW)

    assert preview == {}
