import json
import shutil
from dataclasses import replace

import pytest

from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.pipeline.legacy_vod_games import migrate_legacy_vod_games
from lumia_briefing_room.pipeline.vod_analyze import analyze_vod
from lumia_briefing_room.pipeline.vod_store import load_index, save_index, vod_id
from lumia_briefing_room.pipeline.vod_upgrade import UpgradeError, can_upgrade, upgrade_vod_games

from test_vod_analyze import (  # noqa: F401
    FFMPEG_PATH,
    make_cfg,
    no_result,
    read_frame,
    requires_ffmpeg,
    run,
    screen,
    vod_file,
)


def selection(video, span, floor):
    return 1.0, False


def portraits_none(video, span):
    return None


def legacy_setup(tmp_path, vod_file):
    """예전 방식으로 분석된 상태를 만든다: 클립·색인·판독 캐시만 있고 게임 폴더는 없다."""
    index, cfg = run(tmp_path, vod_file, find_result=lambda v, s, n: screen())
    root = cfg.paths.vod_clips
    shutil.rmtree(cfg.paths.games)
    for game in index["games"]:
        for key in ("gameKey", "fullVideo", "fullStartSec", "fullEndSec"):
            game.pop(key, None)
    index["analysisVersion"] = 5
    save_index(root, index)
    migrate_legacy_vod_games(root, cfg.paths.games)
    return index, cfg


def upgrade(cfg, vod_file, index, **kw):
    args = dict(
        ffmpeg_path=FFMPEG_PATH, root=cfg.paths.vod_clips, games_dir=cfg.paths.games, index=index,
        find_result=lambda v, s, n: replace(screen(), t=56.0), find_portraits=portraits_none, find_selection=selection,
    )
    args.update(kw)
    return upgrade_vod_games(vod_file, cfg, **args)


@requires_ffmpeg
def test_upgrade_makes_full_videos_from_the_known_game_positions_and_cached_reads(vod_file, tmp_path):
    index, cfg = legacy_setup(tmp_path, vod_file)

    created = upgrade(cfg, vod_file, load_index(cfg.paths.vod_clips, vod_id(vod_file)))

    key = f"vod_{vod_id(vod_file)}_g01"
    assert created == [key]
    folder = cfg.paths.games / key
    data = json.loads((folder / "game.json").read_text(encoding="utf-8"))
    assert (folder / "full.mp4").is_file() and data["fullVideo"]["durationSec"] > 40
    assert not data.get("legacy") and data["source"] == "vod"
    assert data["vodStartSec"] == 1.0 and data["matchResult"]["placement"] == 1
    assert (data["spanStartSec"], data["spanEndSec"]) == (5.0, 55.0)
    assert len(data["markers"]) >= 1


@requires_ffmpeg
def test_upgrade_keeps_the_old_clips_and_links_them_to_the_new_candidates(vod_file, tmp_path):
    index, cfg = legacy_setup(tmp_path, vod_file)
    root = cfg.paths.vod_clips
    old = sorted(p.name for p in root.glob("vod_*"))

    upgrade(cfg, vod_file, load_index(root, vod_id(vod_file)))

    assert sorted(p.name for p in root.glob("vod_*")) == old
    data = json.loads((cfg.paths.games / f"vod_{vod_id(vod_file)}_g01" / "game.json").read_text(encoding="utf-8"))
    assert [c["user"].get("savedClipId") for c in data["candidates"]] == index["games"][0]["clipIds"]


@requires_ffmpeg
def test_upgrade_updates_the_index_and_running_twice_changes_nothing(vod_file, tmp_path):
    index, cfg = legacy_setup(tmp_path, vod_file)
    root = cfg.paths.vod_clips

    first = upgrade(cfg, vod_file, load_index(root, vod_id(vod_file)))
    after_first = load_index(root, vod_id(vod_file))
    game_json = (cfg.paths.games / first[0] / "game.json").read_bytes()
    second = upgrade(cfg, vod_file, load_index(root, vod_id(vod_file)))

    assert first and second == []
    assert after_first["games"][0]["gameKey"] == first[0] and after_first["games"][0]["fullVideo"] is True
    assert (cfg.paths.games / first[0] / "game.json").read_bytes() == game_json


@requires_ffmpeg
def test_upgrade_falls_back_to_the_old_result_when_the_result_screen_is_not_found_again(vod_file, tmp_path):
    index, cfg = legacy_setup(tmp_path, vod_file)

    upgrade(cfg, vod_file, load_index(cfg.paths.vod_clips, vod_id(vod_file)), find_result=no_result)

    data = json.loads((cfg.paths.games / f"vod_{vod_id(vod_file)}_g01" / "game.json").read_text(encoding="utf-8"))
    assert data["matchResult"]["placement"] == 1
    assert data["vodEndSec"] == pytest.approx(60.0, abs=0.01)  # 마지막 인게임 프레임 + 10초, 영상 끝에서 자른다


@requires_ffmpeg
def test_upgrade_skips_practice_games(vod_file, tmp_path):
    index, cfg = legacy_setup(tmp_path, vod_file)

    created = upgrade(
        cfg, vod_file, load_index(cfg.paths.vod_clips, vod_id(vod_file)), find_selection=lambda v, s, f: (1.0, True)
    )

    assert created == []
    assert not (cfg.paths.games / f"vod_{vod_id(vod_file)}_g01" / "full.mp4").exists()


@requires_ffmpeg
def test_upgrade_can_be_limited_to_one_game(vod_file, tmp_path):
    index, cfg = legacy_setup(tmp_path, vod_file)

    assert upgrade(cfg, vod_file, load_index(cfg.paths.vod_clips, vod_id(vod_file)), only={9}) == []
    assert len(upgrade(cfg, vod_file, load_index(cfg.paths.vod_clips, vod_id(vod_file)), only={1})) == 1


@requires_ffmpeg
def test_upgrade_refuses_without_the_source_or_the_read_cache(vod_file, tmp_path):
    index, cfg = legacy_setup(tmp_path, vod_file)
    loaded = load_index(cfg.paths.vod_clips, vod_id(vod_file))
    assert can_upgrade(loaded, vod_file, cfg.paths.vod_clips)

    missing = vod_file.with_name("없음.mp4")
    assert not can_upgrade(loaded, missing, cfg.paths.vod_clips)
    with pytest.raises(UpgradeError):
        upgrade(cfg, missing, loaded)

    from lumia_briefing_room.pipeline.vod_store import cache_path

    cache_path(cfg.paths.vod_clips, vod_id(vod_file)).unlink()
    assert not can_upgrade(loaded, vod_file, cfg.paths.vod_clips)
    with pytest.raises(UpgradeError):
        upgrade(cfg, vod_file, loaded)


@requires_ffmpeg
def test_upgrade_reports_progress_and_can_be_cancelled(vod_file, tmp_path):
    import threading

    index, cfg = legacy_setup(tmp_path, vod_file)
    seen = []
    upgrade(cfg, vod_file, load_index(cfg.paths.vod_clips, vod_id(vod_file)), on_progress=lambda f, m: seen.append(f))
    assert seen and seen[-1] == 1.0 and seen == sorted(seen)

    index2, cfg2 = legacy_setup(tmp_path / "again", vod_file)
    cancel = threading.Event()
    cancel.set()
    from lumia_briefing_room.pipeline.vod_analyze import VodCancelled

    with pytest.raises(VodCancelled):
        upgrade(cfg2, vod_file, load_index(cfg2.paths.vod_clips, vod_id(vod_file)), cancel=cancel)


def test_old_clips_with_other_ids_are_linked_to_the_candidate_they_overlap_most():
    from lumia_briefing_room.pipeline import vod_full_games as vfg
    from lumia_briefing_room.pipeline.clip import ClipRange
    from lumia_briefing_room.pipeline.orchestrator import ClipPlan
    from lumia_briefing_room.pipeline.vod_upgrade import _link_old_clips
    from lumia_briefing_room.detect.types import CombatInterval

    iv = CombatInterval(start=110.0, end=130.0, tags=frozenset({"kill"}), k_delta=1, a_delta=0, died=False,
                        day_night="day", confidence=1.0)
    iv2 = CombatInterval(start=310.0, end=330.0, tags=frozenset({"kill"}), k_delta=1, a_delta=0, died=False,
                         day_night="day", confidence=1.0)
    plans = [ClipPlan(ClipRange(105.0, 138.0, "combat"), [iv]), ClipPlan(ClipRange(305.0, 338.0, "combat"), [iv2])]
    cands = vfg.name_vod_candidates(plans, "3df9b3313b4e", 1, duration=900.0)

    linked = _link_old_clips(cands, {"old_a": (300.0, 340.0), "vod_3df9b3313b4e_g01_000105": (104.0, 140.0)}, 0.0)

    assert linked == {cands[0].candidate_id: "vod_3df9b3313b4e_g01_000105", cands[1].candidate_id: "old_a"}
