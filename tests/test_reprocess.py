import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from lumia_briefing_room.config import Config
from lumia_briefing_room.pipeline.playerlog import MatchBoundary
from lumia_briefing_room.pipeline.reprocess import (
    GameRef,
    ReprocessError,
    find_match_end,
    reprocess_game,
)

START = datetime(2026, 9, 21, 10, 58, 21, tzinfo=timezone.utc)
END = datetime(2026, 9, 21, 11, 23, 14, tzinfo=timezone.utc)
SESSION_START = datetime(2026, 9, 21, 10, 53, 57, tzinfo=timezone.utc)
REF = GameRef(session_name="bg_1_20260921_105357", match_start=START.isoformat().replace("+00:00", "Z"))


def write_clip(root: Path, clip_id: str, *, start=REF.match_start, **meta):
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{clip_id}.mp4").write_bytes(b"old-" + clip_id.encode())
    data = {"title": clip_id, "sessionDir": REF.session_name, "matchStartUtc": start, "thumbnailPath": None,
            "deletedAt": None, **meta}
    (root / f"{clip_id}.json").write_text(json.dumps(data), encoding="utf-8")


def make_recording(tmp_path: Path, *, first_segment=1, last_segment=700) -> Path:
    root = tmp_path / "video"
    session_dir = root / REF.session_name
    session_dir.mkdir(parents=True)
    for n in range(first_segment, last_segment + 1):
        (session_dir / f"chunk-stream0-{n:05d}.m4s").write_bytes(b"x")
    return root


def fake_session(directory):
    return SimpleNamespace(directory=directory, start_utc=SESSION_START, segment_duration_sec=3.0)


def call(tmp_path, *, process, boundaries=None, root=None, **kw):
    return reprocess_game(
        clips_dir=tmp_path / "clips", trash_dir=tmp_path / "clips" / ".trash", ref=REF,
        recording_root=root or make_recording(tmp_path), boundaries=boundaries if boundaries is not None
        else [MatchBoundary(start_utc=START, end_utc=END)],
        cfg=Config(), ffmpeg_path=Path("ffmpeg"), process=process, load_session=fake_session, **kw,
    )


def test_find_match_end_matches_the_start_within_a_couple_of_seconds():
    boundaries = [MatchBoundary(START - timedelta(hours=1), START - timedelta(minutes=40)),
                  MatchBoundary(START + timedelta(seconds=1), END)]

    assert find_match_end(START, boundaries) == END
    assert find_match_end(START + timedelta(minutes=5), boundaries) is None
    assert find_match_end(START, [MatchBoundary(START, None)]) is None


def test_reprocess_moves_old_clips_to_trash_then_runs_detection_for_the_logged_match(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "a_01")
    write_clip(clips, "a_02")
    write_clip(clips, "other_01", start="2026-09-20T10:00:00Z")
    calls = []

    def process(session, start, end, cfg, *, ffmpeg_path, clips_dir):
        calls.append((start, end, clips_dir))
        write_clip(clips_dir, "a_01", title="새 클립")
        return [clips_dir / "a_01.json"]

    written = call(tmp_path, process=process)

    assert written == [clips / "a_01.json"]
    assert calls == [(START, END, clips)]
    assert json.loads((clips / "a_01.json").read_text(encoding="utf-8"))["title"] == "새 클립"
    trashed = json.loads((clips / ".trash" / "a_01.json").read_text(encoding="utf-8"))
    assert trashed["title"] == "a_01" and trashed["deletedAt"] is not None
    assert (clips / ".trash" / "a_02.json").exists()
    assert (clips / "other_01.json").exists()


def test_reprocess_prefers_the_recorded_match_end_over_the_log(tmp_path):
    clips = tmp_path / "clips"
    recorded_end = "2026-09-21T11:23:14Z"
    write_clip(clips, "a_01", matchEndUtc=recorded_end)
    seen = []

    call(tmp_path, process=lambda s, st, en, cfg, **kw: seen.append(en) or [], boundaries=[])

    assert seen == [datetime(2026, 9, 21, 11, 23, 14, tzinfo=timezone.utc)]


def test_reprocess_restores_the_old_clips_and_removes_partial_new_ones_when_processing_fails(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "a_01")
    write_clip(clips, "a_02")

    def process(session, start, end, cfg, *, ffmpeg_path, clips_dir):
        write_clip(clips_dir, "a_01", title="반쯤 만든 새 클립")
        raise RuntimeError("ffmpeg 실패")

    with pytest.raises(RuntimeError):
        call(tmp_path, process=process)

    assert json.loads((clips / "a_01.json").read_text(encoding="utf-8"))["title"] == "a_01"
    assert (clips / "a_01.mp4").read_bytes() == b"old-a_01"
    assert (clips / "a_02.json").exists()
    assert not (clips / ".trash" / "a_01.json").exists()


def test_reprocess_replaces_a_same_named_clip_already_sitting_in_the_trash(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "a_01")
    write_clip(clips / ".trash", "a_01", title="예전 휴지통 것", deletedAt="2026-09-20T00:00:00+00:00")

    call(tmp_path, process=lambda *a, **k: [])

    assert json.loads((clips / ".trash" / "a_01.json").read_text(encoding="utf-8"))["title"] == "a_01"


@pytest.mark.parametrize("problem", ["no_clips", "no_recording", "start_deleted", "no_end"])
def test_reprocess_refuses_without_touching_anything_when_it_cannot_run(tmp_path, problem):
    clips = tmp_path / "clips"
    if problem != "no_clips":
        write_clip(clips, "a_01")
    root = make_recording(tmp_path)
    boundaries = None
    if problem == "no_recording":
        root = tmp_path / "empty_video"
        root.mkdir()
    if problem == "start_deleted":
        root = make_recording(tmp_path / "late", first_segment=400, last_segment=700)
    if problem == "no_end":
        boundaries = []

    def process(*a, **k):
        raise AssertionError("실행되면 안 된다")

    with pytest.raises(ReprocessError):
        call(tmp_path, process=process, root=root, boundaries=boundaries)

    if problem != "no_clips":
        assert (clips / "a_01.json").exists() and not (clips / ".trash").exists()


def test_reprocess_carries_labels_from_the_old_clips_to_overlapping_new_ones(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "a_01", userLabel="pvp", labelSource="user", videoOffsetSec=100.0, durationSec=30.0)
    write_clip(clips, "a_02", userLabel="pve", labelSource="user", videoOffsetSec=300.0, durationSec=30.0)

    def process(session, start, end, cfg, *, ffmpeg_path, clips_dir):
        write_clip(clips_dir, "a_01", videoOffsetSec=110.0, durationSec=40.0)
        write_clip(clips_dir, "a_02", videoOffsetSec=900.0, durationSec=20.0)
        return [clips_dir / "a_01.json", clips_dir / "a_02.json"]

    call(tmp_path, process=process)

    first = json.loads((clips / "a_01.json").read_text(encoding="utf-8"))
    second = json.loads((clips / "a_02.json").read_text(encoding="utf-8"))
    assert (first["userLabel"], first["labelSource"]) == ("pvp", "migrated")
    assert second.get("userLabel") is None


def test_reprocess_keeps_the_new_clips_when_label_migration_itself_fails(tmp_path, monkeypatch):
    clips = tmp_path / "clips"
    write_clip(clips, "a_01", userLabel="pvp", videoOffsetSec=0.0, durationSec=30.0)

    def boom(*a, **k):
        raise RuntimeError("이관 실패")

    monkeypatch.setattr("lumia_briefing_room.pipeline.reprocess.migrate_labels", boom)

    written = call(tmp_path, process=lambda s, st, en, cfg, **kw: [write_clip(kw["clips_dir"], "a_01") or kw["clips_dir"] / "a_01.json"])

    assert written == [clips / "a_01.json"] and (clips / "a_01.json").exists()
