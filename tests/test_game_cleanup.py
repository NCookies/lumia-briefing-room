import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lumia_briefing_room.config import RetentionConfig
from lumia_briefing_room.pipeline import game_cleanup as gc

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def cfg(**kw):
    return RetentionConfig(**{"auto_clean_enabled": True, "delete_mode": "permanent", **kw})


def make_game(games: Path, days_ago: float, size: int, *, pinned=False, tags=("kill",), with_video=True) -> Path:
    start = NOW - timedelta(days=days_ago)
    key = f"{start:%Y%m%d_%H%M%S}"
    folder = games / key
    folder.mkdir(parents=True)
    if with_video:
        (folder / "full.mp4").write_bytes(b"x" * size)
    data = {
        "gameKey": key,
        "matchStartUtc": start.isoformat().replace("+00:00", "Z"),
        "fullVideo": {"path": "full.mp4", "sizeBytes": size} if with_video else None,
        "candidates": [{"id": f"{key}_01", "tags": list(tags), "user": {}}],
        "pinned": pinned,
    }
    (folder / "game.json").write_text(json.dumps(data), encoding="utf-8")
    (folder / "result.jpg").write_bytes(b"r")
    return folder


def test_size_limit_picks_the_oldest_full_videos_first(tmp_path):
    games = tmp_path / "games"
    old = make_game(games, 5, 1000)
    mid = make_game(games, 3, 1000)
    make_game(games, 1, 1000)

    plan = gc.plan_game_cleanup(games, cfg(max_total_gb=2500 / 1024**3), now=NOW)

    assert plan.to_delete == [old]
    assert plan.bytes_to_free == 1000
    assert mid not in plan.to_delete


def test_pinned_games_are_never_selected(tmp_path):
    games = tmp_path / "games"
    pinned = make_game(games, 50, 1000, pinned=True)
    make_game(games, 1, 1000)
    plan = gc.plan_game_cleanup(games, cfg(max_age_days=30), now=NOW)
    assert pinned not in plan.to_delete


def test_protected_tags_on_any_candidate_protect_the_game(tmp_path):
    games = tmp_path / "games"
    keep = make_game(games, 50, 1000, tags=("death",))
    drop = make_game(games, 49, 1000, tags=("no_result",))
    plan = gc.plan_game_cleanup(games, cfg(max_age_days=30, protect_tags=["death"]), now=NOW)
    assert plan.to_delete == [drop] and keep not in plan.to_delete


def test_games_without_a_full_video_are_ignored(tmp_path):
    games = tmp_path / "games"
    make_game(games, 50, 0, with_video=False)
    assert gc.plan_game_cleanup(games, cfg(max_age_days=30), now=NOW).to_delete == []


def test_disabled_cleanup_plans_nothing(tmp_path):
    games = tmp_path / "games"
    make_game(games, 50, 1000)
    plan = gc.plan_game_cleanup(games, RetentionConfig(auto_clean_enabled=False, max_age_days=1), now=NOW)
    assert plan.to_delete == []


def test_run_deletes_only_the_video_and_keeps_the_game_record(tmp_path):
    games = tmp_path / "games"
    old = make_game(games, 50, 1000)
    fresh = make_game(games, 1, 1000)

    plan = gc.run_game_cleanup(games, cfg(max_age_days=30), now=NOW)

    assert plan.to_delete == [old]
    assert not (old / "full.mp4").exists()
    assert (fresh / "full.mp4").exists()
    assert (old / "result.jpg").exists()
    data = json.loads((old / "game.json").read_text(encoding="utf-8"))
    assert data["fullVideo"] is None
    assert data["fullVideoDeletedAt"]
    assert data["candidates"][0]["id"].endswith("_01")


def test_run_uses_the_recycle_bin_when_configured(tmp_path, monkeypatch):
    games = tmp_path / "games"
    old = make_game(games, 50, 1000)
    sent = []
    monkeypatch.setattr(gc, "send_to_recycle_bin", lambda paths: sent.extend(paths))

    gc.run_game_cleanup(games, cfg(max_age_days=30, delete_mode="recycle"), now=NOW)

    assert sent == [old / "full.mp4"]


def test_preview_maps_game_keys_to_reason_and_due_time(tmp_path):
    games = tmp_path / "games"
    old = make_game(games, 50, 1000)
    make_game(games, 1, 1000)

    preview = gc.game_cleanup_preview(games, cfg(max_age_days=30), now=NOW)

    assert list(preview) == [old.name]
    assert preview[old.name]["reason"] == "age"
    assert preview[old.name]["dueAt"].startswith("2026-09-10")


def test_missing_games_folder_is_an_empty_plan(tmp_path):
    assert gc.plan_game_cleanup(tmp_path / "nope", cfg(max_age_days=1), now=NOW).to_delete == []


def test_video_file_games_share_the_total_size_limit_with_steam_games(tmp_path):
    games = tmp_path / "games"
    old_steam = make_game(games, 5, 1000)
    vod = games / "vod_3df9b3313b4e_g01"
    vod.mkdir()
    (vod / "full.mp4").write_bytes(b"x" * 1000)
    (vod / "game.json").write_text(
        json.dumps({"gameKey": vod.name, "source": "vod", "matchStartUtc": None, "candidates": []}), encoding="utf-8"
    )

    plan = gc.plan_game_cleanup(games, cfg(max_total_gb=1500 / 1024**3), now=NOW)

    assert plan.to_delete == [old_steam] and plan.bytes_to_free == 1000
