import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lumia_briefing_room.config import Config, PathsConfig
from lumia_briefing_room.pipeline import rebuild_full_video as rb

KEY = "20260928_160025"


class _Session:
    start_utc = datetime(2026, 9, 28, 15, 45, 0, tzinfo=timezone.utc)
    segment_duration_sec = 3.0

    def __init__(self, directory):
        self.directory = directory


def _load(d):
    return _Session(d)


def _setup(tmp_path, *, segments=True, pinned=False):
    games, clips, root = tmp_path / "games", tmp_path / "clips", tmp_path / "steam"
    (games / KEY).mkdir(parents=True)
    clips.mkdir()
    (clips / f"{KEY}_01.json").write_text("{}", encoding="utf-8")
    (games / KEY / "game.json").write_text(json.dumps({
        "gameKey": KEY, "legacy": True, "sessionDir": "bg_1", "matchStartUtc": "2026-09-28T16:00:25.975000Z",
        "matchEndUtc": "2026-09-28T16:18:00Z", "fullVideo": None, "pinned": pinned,
        "candidates": [{"id": f"{KEY}_01", "user": {"savedClipId": f"{KEY}_01"}}],
    }), encoding="utf-8")
    (root / "bg_1").mkdir(parents=True)
    if segments:
        first = int((datetime(2026, 9, 28, 16, 0, 25, tzinfo=timezone.utc) - _Session.start_utc).total_seconds() // 3) + 1
        (root / "bg_1" / f"chunk-stream0-{first:05d}.m4s").write_bytes(b"x")
    return games, clips, root


def _run(games, clips, root, process):
    rb.rebuild_full_video(
        games_dir=games, clips_dir=clips, key=KEY, recording_root=root, cfg=Config(paths=PathsConfig(clips=clips)),
        ffmpeg_path=Path("ffmpeg"), process=process, load_session=_load,
    )


def test_can_rebuild_needs_the_source_and_no_full_video(tmp_path):
    games, clips, root = _setup(tmp_path)
    game = json.loads((games / KEY / "game.json").read_text(encoding="utf-8"))
    assert rb.can_rebuild(game, games, root, _load) is True
    assert rb.can_rebuild(game, games, None, _load) is False
    assert rb.can_rebuild({**game, "fullVideoDeletedAt": "x"}, games, root, _load) is False
    (games / KEY / "full.mp4").write_bytes(b"v")
    assert rb.can_rebuild(game, games, root, _load) is False


def test_can_rebuild_is_false_when_the_source_segments_are_gone(tmp_path):
    games, clips, root = _setup(tmp_path, segments=False)
    game = json.loads((games / KEY / "game.json").read_text(encoding="utf-8"))
    assert rb.can_rebuild(game, games, root, _load) is False


def test_rebuild_runs_the_pipeline_with_the_existing_clips_and_cleans_the_staging(tmp_path):
    games, clips, root = _setup(tmp_path, pinned=True)
    calls = {}

    def fake_process(session, start, end, cfg, **kw):
        calls.update(kw, start=start, end=end)
        (kw["clips_dir"] / "junk.txt").write_text("x")
        (games / KEY / "full.mp4").write_bytes(b"v")
        (games / KEY / "game.json").write_text(
            json.dumps({"gameKey": KEY, "fullVideo": {"path": "full.mp4"}}), encoding="utf-8"
        )
        return []

    _run(games, clips, root, fake_process)

    assert calls["existing_clip_ids"] == {f"{KEY}_01"} and calls["games_dir"] == games
    assert calls["end"] == datetime(2026, 9, 28, 16, 18, tzinfo=timezone.utc)
    assert not calls["clips_dir"].exists()
    assert json.loads((games / KEY / "game.json").read_text(encoding="utf-8"))["pinned"] is True


def test_rebuild_reports_why_no_video_came_out(tmp_path):
    games, clips, root = _setup(tmp_path)

    def failing(session, start, end, cfg, **kw):
        data = json.loads((games / KEY / "game.json").read_text(encoding="utf-8"))
        data["fullVideoError"] = "저장 공간이 부족해 풀영상을 만들지 못했습니다"
        (games / KEY / "game.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(rb.RebuildError, match="저장 공간"):
        _run(games, clips, root, failing)


def test_rebuild_refuses_when_the_source_is_gone(tmp_path):
    games, clips, root = _setup(tmp_path, segments=False)
    with pytest.raises(rb.RebuildError, match="삭제"):
        _run(games, clips, root, lambda *a, **k: None)
