import json
from pathlib import Path

import pytest

from lumia_briefing_room.config import Config, PathsConfig
from lumia_briefing_room.pipeline import clip_from_full as cff


def _game(tmp_path, *, with_video=True):
    folder = tmp_path / "games" / "20260930_002400"
    folder.mkdir(parents=True)
    if with_video:
        (folder / "full.mp4").write_bytes(b"v")
    (folder / "result.jpg").write_bytes(b"r")
    (folder / "portrait_me.jpg").write_bytes(b"p")
    game = {
        "gameKey": "20260930_002400", "sessionDir": "bg_1049590_20260930_000000",
        "sessionStartUtc": "2026-09-30T00:00:00Z", "matchStartUtc": "2026-09-30T00:24:00Z",
        "matchEndUtc": "2026-09-30T00:46:00Z", "gameMode": "battle_royale", "sourceWidth": 2560, "sourceHeight": 1440,
        "matchKills": 2, "matchAssists": 1,
        "matchResult": {"placement": 1, "imagePath": "result.jpg"},
        "portraits": {"me": "portrait_me.jpg", "teammate1": None, "teammate2": None},
        "fullVideo": {"path": "full.mp4", "durationSec": 600.0, "offsetSec": 300.0, "segmentDurationSec": 3.0,
                      "sourceIncomplete": False, "audioStatus": "full"},
    }
    cand = {
        "id": "20260930_002400_01", "start": 100.0, "end": 140.0, "combatStart": 105.0, "combatEnd": 130.0,
        "title": "1일차 낮 교전", "tags": ["kill"], "certain": True, "killDelta": 1, "assistDelta": 0, "died": False,
        "pvpScore": 1.0, "pvpSignals": ["kill_delta"], "gameDay": 1, "dayNight": "day", "user": {},
    }
    return folder, game, cand


@pytest.fixture
def fake_ffmpeg(monkeypatch):
    calls = []

    def run(cmd):
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"clip")

    monkeypatch.setattr(cff, "_run_ffmpeg", run)
    monkeypatch.setattr(cff, "make_thumbnail", lambda clip, out, **kw: out.parent.mkdir(parents=True, exist_ok=True) or out.write_bytes(b"t"))
    return calls


def _save(tmp_path, game, cand, folder):
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips"))
    return cff.save_candidate_clip(
        game, cand, game_folder=folder, clips_dir=tmp_path / "clips", cfg=cfg, ffmpeg_path=Path("ffmpeg")
    )


def test_clip_is_cut_from_the_full_video_with_the_candidate_range(tmp_path, fake_ffmpeg):
    folder, game, cand = _game(tmp_path)

    clip_id = _save(tmp_path, game, cand, folder)

    assert clip_id == "20260930_002400_01"
    cmd = fake_ffmpeg[0]
    assert cmd[cmd.index("-ss") + 1] == "100.000" and cmd[cmd.index("-t") + 1] == "40.000"
    assert str(folder / "full.mp4") in cmd
    assert (tmp_path / "clips" / f"{clip_id}.mp4").read_bytes() == b"clip"


def test_users_adjusted_range_is_used(tmp_path, fake_ffmpeg):
    folder, game, cand = _game(tmp_path)
    cand["user"] = {"start": 90.0, "end": 150.0}
    _save(tmp_path, game, cand, folder)
    cmd = fake_ffmpeg[0]
    assert cmd[cmd.index("-ss") + 1] == "90.000" and cmd[cmd.index("-t") + 1] == "60.000"


def test_metadata_matches_the_existing_clip_format_and_uses_session_based_offsets(tmp_path, fake_ffmpeg):
    folder, game, cand = _game(tmp_path)
    clip_id = _save(tmp_path, game, cand, folder)

    meta = json.loads((tmp_path / "clips" / f"{clip_id}.json").read_text(encoding="utf-8"))

    assert meta["title"] == "1일차 낮 교전" and meta["tags"] == ["kill"]
    assert meta["sessionDir"] == "bg_1049590_20260930_000000"
    assert meta["videoOffsetSec"] == 400.0 and meta["durationSec"] == 40.0
    assert meta["combatStartOffsetSec"] == 405.0 and meta["combatEndOffsetSec"] == 430.0
    assert meta["segmentStart"] == 134
    assert meta["killDelta"] == 1 and meta["pvpScore"] == 1.0 and meta["phaseIndex"] == 0
    assert meta["matchResult"]["imagePath"] == ".thumbs/20260930_002400_result.jpg"
    assert (tmp_path / "clips" / ".thumbs" / "20260930_002400_result.jpg").read_bytes() == b"r"
    assert meta["myCharacterPortraitPath"] == ".thumbs/20260930_002400_portrait_me.jpg"
    assert meta["thumbnailPath"] == f".thumbs/{clip_id}.jpg"
    assert meta["clipUid"]


def test_an_existing_clip_id_is_never_overwritten(tmp_path, fake_ffmpeg):
    folder, game, cand = _game(tmp_path)
    (tmp_path / "clips").mkdir()
    (tmp_path / "clips" / f"{cand['id']}.mp4").write_bytes(b"old")

    clip_id = _save(tmp_path, game, cand, folder)

    assert clip_id == f"{cand['id']}-r2"
    assert (tmp_path / "clips" / f"{cand['id']}.mp4").read_bytes() == b"old"


def test_missing_full_video_raises(tmp_path, fake_ffmpeg):
    folder, game, cand = _game(tmp_path, with_video=False)
    with pytest.raises(cff.FullVideoMissing):
        _save(tmp_path, game, cand, folder)


def test_replacing_a_saved_clip_recuts_the_same_file_and_keeps_its_identity(tmp_path, fake_ffmpeg):
    folder, game, cand = _game(tmp_path)
    clip_id = _save(tmp_path, game, cand, folder)
    json_path = tmp_path / "clips" / f"{clip_id}.json"
    meta = json.loads(json_path.read_text(encoding="utf-8"))
    meta.update({"title": "내가 바꾼 제목", "userLabel": "combat", "pinned": True})
    json_path.write_text(json.dumps(meta), encoding="utf-8")
    uid = meta["clipUid"]

    cand["user"] = {"start": 90.0, "end": 150.0}
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips"))
    same = cff.save_candidate_clip(
        game, cand, game_folder=folder, clips_dir=tmp_path / "clips", cfg=cfg, ffmpeg_path=Path("ffmpeg"), replace_clip_id=clip_id
    )

    assert same == clip_id
    assert not list((tmp_path / "clips").glob("*-r2*"))
    cmd = fake_ffmpeg[-1]
    assert cmd[cmd.index("-ss") + 1] == "90.000" and cmd[cmd.index("-t") + 1] == "60.000"
    assert (tmp_path / "clips" / f"{clip_id}.mp4").read_bytes() == b"clip"
    new_meta = json.loads(json_path.read_text(encoding="utf-8"))
    assert new_meta["durationSec"] == 60.0 and new_meta["videoOffsetSec"] == 390.0
    assert new_meta["title"] == "내가 바꾼 제목" and new_meta["userLabel"] == "combat" and new_meta["pinned"] is True
    assert new_meta["clipUid"] == uid


def test_info_goes_to_the_info_folder_and_video_to_the_video_folder(tmp_path, fake_ffmpeg):
    folder, game, cand = _game(tmp_path)
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips"))
    clip_id = cff.save_candidate_clip(
        game, cand, game_folder=folder, clips_dir=tmp_path / "lib", cfg=cfg, ffmpeg_path=Path("ffmpeg"),
        video_dir=tmp_path / "clips", video_roots=[tmp_path / "clips"],
    )
    assert (tmp_path / "clips" / f"{clip_id}.mp4").read_bytes() == b"clip"
    assert (tmp_path / "lib" / f"{clip_id}.json").exists() and (tmp_path / "lib" / ".thumbs" / f"{clip_id}.jpg").exists()
    assert not (tmp_path / "lib" / f"{clip_id}.mp4").exists() and not (tmp_path / "clips" / f"{clip_id}.json").exists()


def test_replacing_recuts_the_video_where_the_user_moved_it(tmp_path, fake_ffmpeg):
    folder, game, cand = _game(tmp_path)
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips"))
    kw = dict(game_folder=folder, clips_dir=tmp_path / "lib", cfg=cfg, ffmpeg_path=Path("ffmpeg"),
              video_dir=tmp_path / "clips", video_roots=[tmp_path / "clips"])
    clip_id = cff.save_candidate_clip(game, cand, **kw)
    moved = tmp_path / "clips" / "아야" / f"{clip_id}.mp4"
    moved.parent.mkdir()
    (tmp_path / "clips" / f"{clip_id}.mp4").rename(moved)

    cand["user"] = {"start": 90.0, "end": 150.0}
    same = cff.save_candidate_clip(game, cand, replace_clip_id=clip_id, **kw)

    assert same == clip_id
    assert moved.read_bytes() == b"clip" and not (tmp_path / "clips" / f"{clip_id}.mp4").exists()
    assert not list((tmp_path / "clips").rglob("*.replace.mp4"))


def test_a_clip_id_used_by_a_moved_video_is_not_reused(tmp_path, fake_ffmpeg):
    folder, game, cand = _game(tmp_path)
    (tmp_path / "clips" / "sub").mkdir(parents=True)
    (tmp_path / "clips" / "sub" / f"{cand['id']}.mp4").write_bytes(b"old")
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips"))
    clip_id = cff.save_candidate_clip(
        game, cand, game_folder=folder, clips_dir=tmp_path / "lib", cfg=cfg, ffmpeg_path=Path("ffmpeg"),
        video_dir=tmp_path / "clips", video_roots=[tmp_path / "clips"],
    )
    assert clip_id == f"{cand['id']}-r2"
