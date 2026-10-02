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


def make_certain_game(games: Path, days_ago: float, *, saved=(), dismissed=(), certain=("c1", "c2")) -> Path:
    folder = make_game(games, days_ago, 1000)
    data = json.loads((folder / "game.json").read_text(encoding="utf-8"))
    data["candidates"] = [
        {"id": cid, "tags": ["kill"], "certain": True, "start": 0, "end": 5, "user": {}} for cid in certain
    ] + [{"id": "weak", "tags": [], "certain": False, "start": 6, "end": 9, "user": {}}]
    for cand in data["candidates"]:
        if cand["id"] in saved:
            cand["user"]["savedClipId"] = "clip"
        if cand["id"] in dismissed:
            cand["user"]["dismissed"] = True
    (folder / "game.json").write_text(json.dumps(data), encoding="utf-8")
    return folder


def test_preserve_only_picks_certain_unsaved_undismissed_candidates(tmp_path):
    from lumia_briefing_room.pipeline.preserve_before_delete import candidates_to_preserve

    folder = make_certain_game(tmp_path / "games", 50, certain=("c1", "c2", "c3"), saved=("c2",), dismissed=("c3",))
    game = json.loads((folder / "game.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in candidates_to_preserve(game)] == ["c1"]


def test_preserve_saves_each_candidate_before_the_video_goes(tmp_path):
    from lumia_briefing_room.pipeline.preserve_before_delete import preserve_candidates

    games = tmp_path / "games"
    folder = make_certain_game(games, 50)
    game = json.loads((folder / "game.json").read_text(encoding="utf-8"))
    saved = []
    assert preserve_candidates(folder, game, lambda g, c: saved.append(c["id"])) is True
    assert saved == ["c1", "c2"]


def test_preserve_reports_failure_and_stops_at_the_first_error(tmp_path):
    from lumia_briefing_room.pipeline.preserve_before_delete import preserve_candidates

    folder = make_certain_game(tmp_path / "games", 50)
    game = json.loads((folder / "game.json").read_text(encoding="utf-8"))
    calls = []

    def save(g, c):
        calls.append(c["id"])
        raise OSError("disk full")

    assert preserve_candidates(folder, game, save) is False
    assert calls == ["c1"]


def test_run_preserves_before_deleting_when_enabled(tmp_path):
    games = tmp_path / "games"
    old = make_certain_game(games, 50)
    order = []
    plan = gc.run_game_cleanup(
        games, cfg(max_age_days=30, preserve_before_delete=True), now=NOW,
        preserve=lambda folder: order.append(("preserve", (folder / "full.mp4").exists())) or True,
    )
    assert order == [("preserve", True)]
    assert plan.to_delete == [old] and plan.preserve_clips == 2
    assert not (old / "full.mp4").exists()


def test_failed_preserve_holds_back_that_video_but_not_the_others(tmp_path):
    games = tmp_path / "games"
    bad = make_certain_game(games, 50)
    good = make_certain_game(games, 49)
    plan = gc.run_game_cleanup(
        games, cfg(max_age_days=30, preserve_before_delete=True), now=NOW, preserve=lambda folder: folder != bad
    )
    assert (bad / "full.mp4").exists()
    assert not (good / "full.mp4").exists()
    assert plan.to_delete == [good] and plan.held_back == [bad]
    assert plan.bytes_to_free == 1000


def test_enabled_without_a_preserver_deletes_nothing(tmp_path):
    games = tmp_path / "games"
    old = make_certain_game(games, 50)
    plan = gc.run_game_cleanup(games, cfg(max_age_days=30, preserve_before_delete=True), now=NOW)
    assert (old / "full.mp4").exists() and plan.held_back == [old]


def test_disabled_preserve_keeps_the_old_behaviour(tmp_path):
    games = tmp_path / "games"
    old = make_certain_game(games, 50)
    called = []
    plan = gc.run_game_cleanup(games, cfg(max_age_days=30), now=NOW, preserve=lambda f: called.append(f) or False)
    assert called == [] and plan.to_delete == [old] and plan.preserve_clips == 0
    assert not (old / "full.mp4").exists()


def test_dry_run_and_preview_count_the_clips_that_would_be_kept(tmp_path):
    games = tmp_path / "games"
    old = make_certain_game(games, 50, saved=("c1",))
    on = cfg(max_age_days=30, preserve_before_delete=True)
    assert gc.plan_game_cleanup(games, on, now=NOW).preserve_clips == 1
    assert gc.game_cleanup_preview(games, on, now=NOW)[old.name]["preserveCount"] == 1
    off = cfg(max_age_days=30)
    assert gc.plan_game_cleanup(games, off, now=NOW).preserve_clips == 0
    assert gc.game_cleanup_preview(games, off, now=NOW)[old.name]["preserveCount"] == 0


def test_make_preserver_saves_through_save_and_mark(tmp_path, monkeypatch):
    from lumia_briefing_room.config import Config, PathsConfig
    from lumia_briefing_room.pipeline import preserve_before_delete as pbd

    games = tmp_path / "games"
    folder = make_certain_game(games, 50, saved=("c2",))
    cfg_ = Config(paths=PathsConfig(clips=tmp_path / "clips", games=games))
    saved = []
    monkeypatch.setattr(pbd, "save_and_mark", lambda gd, key, game, cand, **kw: saved.append((key, cand["id"])))

    assert pbd.make_preserver(cfg_, Path("ffmpeg"))(folder) is True
    assert saved == [(folder.name, "c1")]
    assert pbd.make_preserver(cfg_, None)(folder) is False


def test_restored_full_video_is_relinked_with_old_duration(tmp_path):
    from lumia_briefing_room.pipeline.game_files import load_game, relink_restored_full_video

    games = tmp_path / "games"
    folder = make_game(games, 1, 500)
    data = json.loads((folder / "game.json").read_text(encoding="utf-8"))
    data["fullVideo"]["durationSec"] = 321.0
    (folder / "game.json").write_text(json.dumps(data), encoding="utf-8")
    gc.delete_full_video(folder, mode="permanent")
    assert load_game(games, folder.name)["fullVideo"] is None

    (folder / "full.mp4").write_bytes(b"x" * 700)
    assert relink_restored_full_video(games, folder.name) is True
    game = load_game(games, folder.name)
    assert game["fullVideo"]["durationSec"] == 321.0 and game["fullVideo"]["sizeBytes"] == 700
    assert not game.get("fullVideoDeletedAt")


def test_relink_probes_duration_when_no_backup_and_ignores_missing_file(tmp_path):
    from lumia_briefing_room.pipeline.game_files import load_game, relink_restored_full_video

    games = tmp_path / "games"
    folder = make_game(games, 1, 500, with_video=False)
    data = json.loads((folder / "game.json").read_text(encoding="utf-8"))
    data["fullVideoDeletedAt"] = "2026-10-02T00:41:29Z"
    (folder / "game.json").write_text(json.dumps(data), encoding="utf-8")
    assert relink_restored_full_video(games, folder.name, probe=lambda p: 99.0) is False

    (folder / "full.mp4").write_bytes(b"x" * 10)
    assert relink_restored_full_video(games, folder.name, probe=lambda p: 99.0) is True
    assert load_game(games, folder.name)["fullVideo"] == {"path": "full.mp4", "sizeBytes": 10, "durationSec": 99.0}
