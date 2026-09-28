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
            **meta}
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


def call(tmp_path, *, process, boundaries=None, root=None, cfg=None, **kw):
    return reprocess_game(
        clips_dir=tmp_path / "clips", ref=REF,
        recording_root=root or make_recording(tmp_path), boundaries=boundaries if boundaries is not None
        else [MatchBoundary(start_utc=START, end_utc=END)],
        cfg=cfg or Config(), ffmpeg_path=Path("ffmpeg"), process=process, load_session=fake_session, **kw,
    )


def test_find_match_end_matches_the_start_within_a_couple_of_seconds():
    boundaries = [MatchBoundary(START - timedelta(hours=1), START - timedelta(minutes=40)),
                  MatchBoundary(START + timedelta(seconds=1), END)]

    assert find_match_end(START, boundaries) == END
    assert find_match_end(START + timedelta(minutes=5), boundaries) is None
    assert find_match_end(START, [MatchBoundary(START, None)]) is None


def test_reprocess_writes_new_clips_into_a_staging_dir_then_deletes_old_ones_on_success(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "a_01")
    write_clip(clips, "a_02")
    write_clip(clips, "other_01", start="2026-09-20T10:00:00Z")
    calls = []

    def process(session, start, end, cfg, *, ffmpeg_path, clips_dir):
        calls.append((start, end, clips_dir))
        assert clips_dir != clips  # 실제 클립 폴더가 아니라 스테이징에 쓴다
        write_clip(clips_dir, "a_01", title="새 클립")
        return [clips_dir / "a_01.json"]

    written = call(tmp_path, process=process, cfg=Config())

    assert written == [clips / "a_01.json"]
    assert calls[0][0] == START and calls[0][1] == END
    assert json.loads((clips / "a_01.json").read_text(encoding="utf-8"))["title"] == "새 클립"
    assert not (clips / "a_02.json").exists()  # 기존 클립은 삭제됐다(기본: 휴지통)
    assert (clips / "other_01.json").exists()
    assert not any((tmp_path / "clips" / ".staging").glob("**/*"))


def test_reprocess_prefers_the_recorded_match_end_over_the_log(tmp_path):
    clips = tmp_path / "clips"
    recorded_end = "2026-09-21T11:23:14Z"
    write_clip(clips, "a_01", matchEndUtc=recorded_end)
    seen = []

    def process(session, start, end, cfg, *, ffmpeg_path, clips_dir):
        seen.append(end)
        write_clip(clips_dir, "a_01")
        return [clips_dir / "a_01.json"]

    call(tmp_path, process=process, boundaries=[])

    assert seen == [datetime(2026, 9, 21, 11, 23, 14, tzinfo=timezone.utc)]


def test_reprocess_keeps_old_clips_untouched_when_processing_fails(tmp_path):
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
    assert not any((clips / ".staging").glob("**/*.json")) if (clips / ".staging").exists() else True


def test_reprocess_keeps_old_clips_untouched_when_no_clips_are_found(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "a_01")

    with pytest.raises(ReprocessError):
        call(tmp_path, process=lambda *a, **k: [])

    assert (clips / "a_01.json").exists()


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
        assert (clips / "a_01.json").exists()


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


def test_reprocess_carries_a_manually_locked_match_result_to_the_new_clips(tmp_path):
    clips = tmp_path / "clips"
    locked = {"placement": 1, "total": 8, "outcome": "최종 생존"}
    write_clip(clips, "a_01", matchResult=locked, matchResultSource="manual")
    write_clip(clips, "a_02", matchResult=locked, matchResultSource="manual")

    def process(session, start, end, cfg, *, ffmpeg_path, clips_dir):
        write_clip(clips_dir, "a_01", matchResult={"placement": 4, "total": 8}, matchResultSource=None)
        return [clips_dir / "a_01.json"]

    call(tmp_path, process=process)

    new_meta = json.loads((clips / "a_01.json").read_text(encoding="utf-8"))
    assert new_meta["matchResult"] == locked
    assert new_meta["matchResultSource"] == "manual"


def test_reprocess_leaves_new_clips_alone_when_nothing_was_locked(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "a_01")

    def process(session, start, end, cfg, *, ffmpeg_path, clips_dir):
        write_clip(clips_dir, "a_01", matchResult={"placement": 4, "total": 8})
        return [clips_dir / "a_01.json"]

    call(tmp_path, process=process)

    new_meta = json.loads((clips / "a_01.json").read_text(encoding="utf-8"))
    assert new_meta["matchResult"] == {"placement": 4, "total": 8}
    assert "matchResultSource" not in new_meta or new_meta["matchResultSource"] is None


def test_reprocess_keeps_the_new_clips_when_label_migration_itself_fails(tmp_path, monkeypatch):
    clips = tmp_path / "clips"
    write_clip(clips, "a_01", userLabel="pvp", videoOffsetSec=0.0, durationSec=30.0)

    def boom(*a, **k):
        raise RuntimeError("이관 실패")

    monkeypatch.setattr("lumia_briefing_room.pipeline.reprocess.migrate_labels", boom)

    written = call(tmp_path, process=lambda s, st, en, cfg, **kw: [write_clip(kw["clips_dir"], "a_01") or kw["clips_dir"] / "a_01.json"])

    assert written == [clips / "a_01.json"] and (clips / "a_01.json").exists()


def test_reprocess_permanent_mode_deletes_old_clip_files(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "a_01")
    cfg = Config()
    cfg.ui.delete_mode = "permanent"

    def process(session, start, end, cfg, *, ffmpeg_path, clips_dir):
        write_clip(clips_dir, "a_01", title="새 클립")
        return [clips_dir / "a_01.json"]

    call(tmp_path, process=process, cfg=cfg)

    assert json.loads((clips / "a_01.json").read_text(encoding="utf-8"))["title"] == "새 클립"


def test_reprocess_recycle_mode_sends_old_clip_files_to_recycle_bin(tmp_path, monkeypatch):
    from lumia_briefing_room.pipeline import delete_helper

    clips = tmp_path / "clips"
    write_clip(clips, "a_01")
    sent = []
    monkeypatch.setattr(delete_helper, "_send2trash", lambda path: sent.append(Path(path).name))
    cfg = Config()
    cfg.ui.delete_mode = "recycle"

    def process(session, start, end, cfg, *, ffmpeg_path, clips_dir):
        write_clip(clips_dir, "a_01", title="새 클립")
        return [clips_dir / "a_01.json"]

    call(tmp_path, process=process, cfg=cfg)

    assert set(sent) == {"a_01.json", "a_01.mp4"}
