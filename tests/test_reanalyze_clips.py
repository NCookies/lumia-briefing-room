from pathlib import Path

from lumia_briefing_room.config import Config
from lumia_briefing_room.pipeline.reanalyze_clips import auto_saved_clip_ids, refresh_auto_clips
from test_reanalyze_game import KEY, new_game, seed


def test_only_clips_linked_to_auto_candidates_and_in_the_auto_folder_count_as_auto():
    game = {"candidates": [
        {"id": "a", "user": {"savedClipId": "auto1"}}, {"id": "b", "user": {"savedClipId": "kept1"}}, {"id": "c", "user": {}},
    ], "userCandidates": [{"id": "u", "user": {"savedClipId": "auto2"}}]}
    assert auto_saved_clip_ids(game, is_auto=lambda cid: cid.startswith("auto")) == {"auto1"}


def test_auto_clips_are_deleted_then_unsaved_candidates_are_cut_again_when_save_mode_is_auto(tmp_path):
    games, _ = seed(tmp_path)
    from lumia_briefing_room.pipeline.game_files import update_game
    update_game(games, KEY, lambda d: d.update(new_game()))
    deleted, saved = [], []
    cfg = Config()
    cfg.clip.save_mode = "auto"
    made, failed = refresh_auto_clips(
        games, KEY, ["auto1"], cfg=cfg, ffmpeg_path=Path("ffmpeg"), delete=deleted.append,
        save=lambda gdir, key, game, cand, **kw: saved.append((cand["id"], kw["manual"])),
    )
    assert deleted == ["auto1"] and (made, failed) == (3, 0)
    assert saved == [(f"{KEY}_01", False), (f"{KEY}_02", False), (f"{KEY}_03", False)]


def test_manual_save_mode_only_deletes(tmp_path):
    games, _ = seed(tmp_path)
    cfg = Config()
    cfg.clip.save_mode = "manual"
    deleted = []
    assert refresh_auto_clips(games, KEY, ["x"], cfg=cfg, ffmpeg_path=Path("f"), delete=deleted.append, save=lambda *a, **k: 1 / 0) == (0, 0)
    assert deleted == ["x"]


def test_a_failing_cut_is_counted_and_does_not_stop_the_rest(tmp_path):
    games, _ = seed(tmp_path)
    from lumia_briefing_room.pipeline.game_files import update_game
    update_game(games, KEY, lambda d: d.update(new_game()))
    cfg = Config()
    cfg.clip.save_mode = "auto"
    calls = []

    def save(gdir, key, game, cand, **kw):
        calls.append(cand["id"])
        if cand["id"].endswith("_02"):
            raise OSError("disk")

    assert refresh_auto_clips(games, KEY, [], cfg=cfg, ffmpeg_path=Path("f"), delete=lambda c: None, save=save) == (2, 1)
    assert len(calls) == 3
