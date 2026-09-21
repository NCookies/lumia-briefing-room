import json
import threading
from datetime import datetime, timedelta, timezone

from lumia_briefing_room.config import RetentionConfig
from lumia_briefing_room.pipeline.cleanup import cleanup_loop, plan_cleanup, run_cleanup

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def write_clip(root, clip_id, *, days_ago=0, size=6000, thumb=True, **meta):
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{clip_id}.mp4").write_bytes(b"x" * size)
    data = {
        "title": clip_id, "tags": ["kill"], "pinned": False, "deletedAt": None,
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

    plan = plan_cleanup(tmp_path / "clips", tmp_path / "trash", RetentionConfig(max_age_days=1), now=NOW)

    assert plan.to_trash == [] and plan.to_purge == []


def test_max_age_moves_old_unprotected_clips_to_trash(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "old", days_ago=40)
    write_clip(clips, "fresh", days_ago=2)
    write_clip(clips, "pinned_old", days_ago=40, pinned=True)
    write_clip(clips, "death_old", days_ago=40, tags=["death"])

    plan = run_cleanup(clips, tmp_path / "trash", cfg(max_age_days=30), now=NOW)

    assert names(plan.to_trash) == ["old"]
    assert not (clips / "old.json").exists()
    assert (tmp_path / "trash" / "old.json").exists()
    assert (clips / "fresh.json").exists() and (clips / "pinned_old.json").exists()
    assert (clips / "death_old.json").exists()
    trashed = json.loads((tmp_path / "trash" / "old.json").read_text(encoding="utf-8"))
    assert trashed["deletedAt"] is not None


def test_max_count_keeps_the_newest(tmp_path):
    clips = tmp_path / "clips"
    for i, days in enumerate([5, 4, 3, 2, 1]):
        write_clip(clips, f"c{i}", days_ago=days)

    plan = plan_cleanup(clips, tmp_path / "trash", cfg(max_count=2), now=NOW)

    assert names(plan.to_trash) == ["c0", "c1", "c2"]


def test_max_total_gb_frees_oldest_until_under_the_limit(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "a", days_ago=3, size=6000)
    write_clip(clips, "b", days_ago=2, size=6000)
    write_clip(clips, "c", days_ago=1, size=6000)

    plan = plan_cleanup(clips, tmp_path / "trash", cfg(max_total_gb=13000 / 1024**3), now=NOW)

    assert names(plan.to_trash) == ["a"]
    assert plan.bytes_to_free == 6000


def test_age_uses_game_time_not_file_modification_time(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "old_but_just_edited", days_ago=90)

    plan = plan_cleanup(clips, tmp_path / "trash", cfg(max_age_days=30), now=NOW)

    assert names(plan.to_trash) == ["old_but_just_edited"]


def test_trash_older_than_grace_period_is_purged_with_its_files(tmp_path):
    trash = tmp_path / "trash"
    write_clip(trash, "expired", deletedAt=iso(40))
    write_clip(trash, "recent", deletedAt=iso(10))

    plan = run_cleanup(tmp_path / "clips", trash, cfg(trash_days=30), now=NOW)

    assert names(plan.to_purge) == ["expired"]
    assert not (trash / "expired.json").exists() and not (trash / "expired.mp4").exists()
    assert not (trash / ".thumbs" / "expired.jpg").exists()
    assert (trash / "recent.json").exists()


def test_permanent_delete_mode_removes_instead_of_trashing(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "old", days_ago=40)

    run_cleanup(clips, tmp_path / "trash", cfg(max_age_days=30, delete_mode="permanent"), now=NOW)

    assert not (clips / "old.json").exists() and not (clips / "old.mp4").exists()
    assert not (tmp_path / "trash" / "old.json").exists()


def test_dry_run_plans_without_touching_files(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "old", days_ago=40)

    plan = plan_cleanup(clips, tmp_path / "trash", cfg(max_age_days=30), now=NOW)

    assert names(plan.to_trash) == ["old"]
    assert (clips / "old.json").exists() and not (tmp_path / "trash").exists()


def test_orphan_result_images_are_removed_but_referenced_ones_stay(tmp_path):
    clips = tmp_path / "clips"
    kept_image = clips / ".thumbs" / "20260920_100000_result.jpg"
    orphan = clips / ".thumbs" / "20260919_100000_result.jpg"
    kept_image.parent.mkdir(parents=True)
    kept_image.write_bytes(b"j")
    orphan.write_bytes(b"j")
    write_clip(clips, "a", days_ago=1, matchResult={"imagePath": str(kept_image)})

    run_cleanup(clips, tmp_path / "trash", cfg(), now=NOW)

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
    from lumia_briefing_room.config import Config, PathsConfig, save_config
    from lumia_briefing_room.pipeline.cleanup import make_cleanup_runner

    clips = tmp_path / "clips"
    write_clip(clips, "old", days_ago=400)
    config_path = tmp_path / "config.json"
    save_config(Config(paths=PathsConfig(clips=clips)), config_path)
    runner = make_cleanup_runner(config_path)

    assert runner().to_trash == []

    save_config(
        Config(paths=PathsConfig(clips=clips), retention=RetentionConfig(auto_clean_enabled=True, max_age_days=30)),
        config_path,
    )
    plan = runner()

    assert names(plan.to_trash) == ["old"]
    assert (clips / ".trash" / "old.json").exists()
