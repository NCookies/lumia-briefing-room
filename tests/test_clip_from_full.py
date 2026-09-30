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
