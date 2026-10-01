import json
import subprocess
from pathlib import Path

import pytest

from lumia_briefing_room.config import Config
from lumia_briefing_room.pipeline.game_files import load_game, update_game
from lumia_briefing_room.pipeline.reanalyze_game import (
    REANALYZE_CANDIDATES,
    REANALYZE_FULL,
    ReanalyzeError,
    carry_over,
    reanalyze_game,
    reanalyze_mode,
)
from test_vod_analyze import (  # noqa: F401  (vod_file 픽스처)
    FFMPEG_PATH,
    make_cfg,
    no_result,
    read_frame,
    requires_ffmpeg,
    screen,
    vod_file,
)

KEY = "20260930_002400"


def cand(cid, start, end, user=None, title=None):
    return {"id": cid, "start": start, "end": end, "combatStart": start + 5, "combatEnd": end - 5, "title": title or cid,
            "tags": ["kill"], "certain": True, "user": user or {}}


def old_game(**over):
    game = {
        "gameKey": KEY, "matchStartUtc": "2026-09-30T00:24:00Z", "matchEndUtc": "2026-09-30T00:46:00Z",
        "sessionDir": "bg_1", "sessionStartUtc": "2026-09-30T00:00:00Z", "gameMode": "battle_royale",
        "sourceWidth": 2560, "sourceHeight": 1440, "pinned": True,
        "matchResult": {"placement": 3, "imagePath": "result.jpg"},
        "portraits": {"me": "portrait_me.jpg", "teammate1": None, "teammate2": None},
        "fullVideo": {"path": "full.mp4", "sizeBytes": 10, "durationSec": 600.0, "offsetSec": 300.0,
                      "segmentDurationSec": 3.0, "sourceIncomplete": False, "audioStatus": "full"},
        "candidates": [
            cand(f"{KEY}_01", 100, 140, {"savedClipId": "clip_a", "savedStart": 100.0, "savedEnd": 140.0}),
            cand(f"{KEY}_02", 300, 330, {"dismissed": True, "title": "내가 붙인 이름"}),
            cand(f"{KEY}_03", 500, 520, {"savedClipId": "clip_far", "savedStart": 505.0, "savedEnd": 515.0}),
        ],
        "userCandidates": [{"id": f"{KEY}_u1", "start": 200.0, "end": 230.0, "title": "직접 추가한 구간", "tags": [], "certain": False, "user": {}}],
        "markers": [],
    }
    game.update(over)
    return game


def seed(tmp_path, game=None, *, full=True):
    games = tmp_path / "games"
    folder = games / KEY
    folder.mkdir(parents=True)
    if full:
        (folder / "full.mp4").write_bytes(b"OLDFULL")
    (folder / "result.jpg").write_bytes(b"oldresult")
    (folder / "portrait_me.jpg").write_bytes(b"oldme")
    (folder / "game.json").write_text(json.dumps(game or old_game()), encoding="utf-8")
    library = tmp_path / "library"
    library.mkdir()
    for clip_id in ("clip_a", "clip_far"):
        (library / f"{clip_id}.json").write_text("{}", encoding="utf-8")
    return games, library


def new_game(offset=300.0, **over):
    data = {
        "gameKey": KEY, "matchStartUtc": "2026-09-30T00:24:00Z", "matchEndUtc": "2026-09-30T00:46:00Z",
        "sessionDir": "bg_1", "sessionStartUtc": "2026-09-30T00:00:00Z", "gameMode": "battle_royale",
        "matchResult": {"placement": 1, "imagePath": "result.jpg"},
        "portraits": {"me": "portrait_me.jpg", "teammate1": "portrait_teammate1.jpg", "teammate2": None},
        "fullVideo": {"path": "full.mp4", "sizeBytes": 20, "durationSec": 620.0, "offsetSec": offset,
                      "segmentDurationSec": 3.0, "sourceIncomplete": False, "audioStatus": "full"},
        "candidates": [cand(f"{KEY}_01", 98, 141), cand(f"{KEY}_02", 302, 340), cand(f"{KEY}_03", 400, 420)],
        "userCandidates": [], "markers": [{"t": 120.0, "kind": "kill"}],
    }
    data.update(over)
    return data


def fake_process(data, *, make_full=True):
    def process(session, start, end, cfg, *, games_dir, clips_dir, existing_clip_ids, **kw):
        folder = games_dir / KEY
        folder.mkdir(parents=True)
        if make_full:
            (folder / "full.mp4").write_bytes(b"NEWFULL")
        (folder / "result.jpg").write_bytes(b"newresult")
        (folder / "portrait_teammate1.jpg").write_bytes(b"newmate")
        body = dict(data)
        if not make_full:
            body = {**body, "fullVideo": None, "fullVideoError": "저장 공간이 부족합니다"}
        (folder / "game.json").write_text(json.dumps(body), encoding="utf-8")
        process.known = set(existing_clip_ids)
        return []

    return process


def source_ok(game, recording_root, load_session):
    return object(), None, None


def run_full(tmp_path, games, library, process, **kw):
    return reanalyze_game(
        games_dir=games, clips_dir=library, key=KEY, recording_root=tmp_path / "rec", cfg=Config(), ffmpeg_path=Path("ffmpeg"),
        staging_dir=tmp_path / "staging", process=process, locate_source=source_ok, **kw,
    )


def test_mode_prefers_the_source_recording_then_the_local_full_video_then_gives_up(tmp_path):
    games, _ = seed(tmp_path)
    game = load_game(games, KEY)
    assert reanalyze_mode(game, games, tmp_path / "rec", locate_source=source_ok) == REANALYZE_FULL

    def no_source(g, root, loader):
        raise ReanalyzeError("원본 없음")

    assert reanalyze_mode(game, games, tmp_path / "rec", locate_source=no_source) == REANALYZE_CANDIDATES
    (games / KEY / "full.mp4").unlink()
    assert reanalyze_mode(game, games, tmp_path / "rec", locate_source=no_source) is None


def test_full_mode_replaces_the_full_video_and_candidates_but_keeps_pins_and_saved_clips(tmp_path):
    games, library = seed(tmp_path)
    process = fake_process(new_game())
    assert run_full(tmp_path, games, library, process) == REANALYZE_FULL
    folder = games / KEY
    assert (folder / "full.mp4").read_bytes() == b"NEWFULL" and (folder / "result.jpg").read_bytes() == b"newresult"
    assert (folder / "portrait_teammate1.jpg").exists()
    game = load_game(games, KEY)
    assert game["pinned"] is True and game["matchResult"]["placement"] == 1 and game["markers"]
    assert process.known == {"clip_a", "clip_far"}, "보관한 클립은 다시 자르지 않는다"
    assert not (tmp_path / "staging").exists() or not any((tmp_path / "staging").iterdir())


def test_full_mode_relinks_saved_clips_to_the_overlapping_new_candidate_with_the_saved_range(tmp_path):
    games, library = seed(tmp_path)
    run_full(tmp_path, games, library, fake_process(new_game()))
    by_id = {c["id"]: c for c in load_game(games, KEY)["candidates"]}
    linked = by_id[f"{KEY}_01"]["user"]
    assert linked["savedClipId"] == "clip_a" and linked["savedStart"] == 100.0 and linked["savedEnd"] == 140.0
    assert linked["start"] == 100.0 and linked["end"] == 140.0, "저장 범위로 맞춰 두어 고친 것으로 보이지 않는다"
    assert not by_id[f"{KEY}_02"]["user"], "무시·이름 수정 같은 후보 수정은 초기화된다"


def test_a_saved_clip_without_an_overlapping_new_candidate_becomes_a_user_candidate(tmp_path):
    games, library = seed(tmp_path)
    run_full(tmp_path, games, library, fake_process(new_game()))
    game = load_game(games, KEY)
    orphans = [c for c in game["userCandidates"] if (c.get("user") or {}).get("savedClipId") == "clip_far"]
    assert len(orphans) == 1 and (orphans[0]["start"], orphans[0]["end"]) == (505.0, 515.0)
    assert orphans[0]["title"] == f"{KEY}_03"
    assert all(not (c.get("user") or {}).get("savedClipId") == "clip_far" for c in game["candidates"])


def test_full_mode_moves_user_candidates_to_the_new_time_base(tmp_path):
    games, library = seed(tmp_path)
    run_full(tmp_path, games, library, fake_process(new_game(offset=290.0)))
    manual = [c for c in load_game(games, KEY)["userCandidates"] if c["title"] == "직접 추가한 구간"]
    assert [(c["start"], c["end"]) for c in manual] == [(210.0, 240.0)], "오프셋이 10초 앞당겨졌으니 10초 뒤로"


def test_a_failed_full_video_leaves_the_old_game_untouched(tmp_path):
    games, library = seed(tmp_path)
    with pytest.raises(ReanalyzeError, match="저장 공간"):
        run_full(tmp_path, games, library, fake_process(new_game(), make_full=False))
    folder = games / KEY
    assert (folder / "full.mp4").read_bytes() == b"OLDFULL"
    assert load_game(games, KEY)["matchResult"]["placement"] == 3
    assert not (tmp_path / "staging").exists() or not any((tmp_path / "staging").iterdir())


def test_the_old_result_and_portraits_are_kept_when_the_new_reading_found_nothing(tmp_path):
    games, library = seed(tmp_path)
    data = new_game(matchResult=None, portraits={"me": None, "teammate1": None, "teammate2": None})
    run_full(tmp_path, games, library, fake_process(data))
    game = load_game(games, KEY)
    assert game["matchResult"]["placement"] == 3 and game["portraits"]["me"] == "portrait_me.jpg"
    assert (games / KEY / "portrait_me.jpg").read_bytes() == b"oldme"


def test_a_manually_fixed_result_survives_reanalysis(tmp_path):
    games, library = seed(tmp_path, old_game(matchResult={"placement": 5}, matchResultSource="manual"))
    run_full(tmp_path, games, library, fake_process(new_game()))
    game = load_game(games, KEY)
    assert game["matchResult"]["placement"] == 5 and game["matchResultSource"] == "manual"


def test_a_user_title_survives_reanalysis(tmp_path):
    games, library = seed(tmp_path, old_game(title="내 제목"))
    run_full(tmp_path, games, library, fake_process(new_game()))
    assert load_game(games, KEY)["title"] == "내 제목"


def test_nothing_to_analyze_is_an_error(tmp_path):
    games, library = seed(tmp_path, full=False)

    def no_source(g, root, loader):
        raise ReanalyzeError("원본 없음")

    with pytest.raises(ReanalyzeError, match="다시 분석할 수 없습니다"):
        reanalyze_game(
            games_dir=games, clips_dir=library, key=KEY, recording_root=None, cfg=Config(), ffmpeg_path=Path("ffmpeg"),
            staging_dir=tmp_path / "staging", locate_source=no_source,
        )


def test_carry_over_drops_user_candidates_that_fall_outside_the_new_video():
    old = old_game(userCandidates=[{"id": f"{KEY}_u1", "start": 10.0, "end": 40.0, "title": "앞", "tags": [], "certain": False, "user": {}}])
    new = new_game(offset=400.0)
    carry_over(old, new)
    assert [c["title"] for c in new["userCandidates"] if c["title"] == "앞"] == [], "새 풀영상이 100초 뒤에 시작해 앞 구간은 영상 밖이다"


@requires_ffmpeg
def test_candidates_mode_rereads_candidates_result_and_portraits_from_the_local_full_video(vod_file, tmp_path):
    games, library = seed(tmp_path)
    (games / KEY / "full.mp4").write_bytes(vod_file.read_bytes())
    update_game(games, KEY, lambda d: (d["fullVideo"].update(durationSec=60.0, offsetSec=0.0), d.update(userCandidates=[{"id": f"{KEY}_u1", "start": 30.0, "end": 50.0, "title": "직접 추가한 구간", "tags": [], "certain": False, "user": {}}])))

    def no_source(g, root, loader):
        raise ReanalyzeError("원본 없음")

    cfg = make_cfg(tmp_path)
    mode = reanalyze_game(
        games_dir=games, clips_dir=library, key=KEY, recording_root=None, cfg=cfg, ffmpeg_path=FFMPEG_PATH,
        staging_dir=tmp_path / "staging", locate_source=no_source, read_frame=read_frame,
        find_result=lambda v, s, n: screen(), find_portraits=lambda v, s: None,
    )
    assert mode == REANALYZE_CANDIDATES
    game = load_game(games, KEY)
    assert (games / KEY / "full.mp4").read_bytes() == vod_file.read_bytes(), "풀영상은 그대로"
    ids = [c["id"] for c in game["candidates"]]
    assert ids and ids[0] == f"{KEY}_01"
    first = game["candidates"][0]
    assert "kill" in first["tags"] and 15 <= first["start"] <= 30
    assert game["matchResult"]["placement"] == 1 and game["markers"]
    assert game["portraits"]["me"] == "portrait_me.jpg", "못 읽은 초상화는 이전 것을 유지"
    assert game["pinned"] is True and game["userCandidates"][0]["title"] == "직접 추가한 구간"
    assert not (tmp_path / "staging").exists() or not any((tmp_path / "staging").iterdir())


@requires_ffmpeg
def test_candidates_mode_with_no_game_in_the_video_keeps_the_old_candidates(vod_file, tmp_path):
    games, library = seed(tmp_path)
    (games / KEY / "full.mp4").write_bytes(vod_file.read_bytes())

    def no_source(g, root, loader):
        raise ReanalyzeError("원본 없음")

    from lumia_briefing_room.detect.types import FrameState

    with pytest.raises(ReanalyzeError, match="찾지 못했습니다"):
        reanalyze_game(
            games_dir=games, clips_dir=library, key=KEY, recording_root=None, cfg=make_cfg(tmp_path), ffmpeg_path=FFMPEG_PATH,
            staging_dir=tmp_path / "staging", locate_source=no_source,
            read_frame=lambda frame, t: FrameState(t=round(t), combat=None, face_value=None, face_sat=None, k=None, a=None, day_night=None),
            find_result=no_result,
        )
    assert len(load_game(games, KEY)["candidates"]) == 3


def test_auto_saved_clips_are_not_carried_over_but_user_archived_ones_are(tmp_path):
    games, library = seed(tmp_path)
    process = fake_process(new_game())
    run_full(tmp_path, games, library, process, auto_clip_ids={"clip_a"})
    assert process.known == {"clip_far"}
    saved = {c["id"]: (c.get("user") or {}).get("savedClipId") for c in load_game(games, KEY)["candidates"]}
    assert "clip_a" not in saved.values()
    assert any(v == "clip_far" for v in saved.values()) or any(
        (c.get("user") or {}).get("savedClipId") == "clip_far" for c in load_game(games, KEY)["userCandidates"]
    )
