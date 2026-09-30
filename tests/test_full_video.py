import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lumia_briefing_room.pipeline import full_video as fv
from lumia_briefing_room.pipeline.clip import ClipCutError, CutResult
from lumia_briefing_room.video.segments import SegmentRange

START = datetime(2026, 9, 30, 0, 0, 0, tzinfo=timezone.utc)


class Session:
    start_utc = START
    segment_duration_sec = 3.0

    def __init__(self, directory: Path):
        self.directory = directory


def _make_session(tmp_path, n=6, size=1000):
    d = tmp_path / "bg_1049590_20260930_000000"
    d.mkdir()
    for i in range(1, n + 1):
        for s in (0, 1):
            (d / f"chunk-stream{s}-{i:05d}.m4s").write_bytes(b"x" * size)
    (d / "chunk-stream0-00099.m4s").write_bytes(b"x" * size)
    (d / "init-stream0.m4s").write_bytes(b"x" * size)
    return Session(d)


def _run(session, folder, tmp_path, monkeypatch, *, cut, free=10 * 2**30):
    monkeypatch.setattr(fv, "cut_clip", cut)
    monkeypatch.setattr(fv, "_free_bytes", lambda f: free)
    return fv.cut_full_video(
        session, SegmentRange(2, 5), START + timedelta(seconds=3), START + timedelta(seconds=14), folder,
        ffmpeg_path=Path("ffmpeg"), include_audio=True, tmp_dir=tmp_path,
    )


def test_estimate_counts_only_chunks_inside_the_range(tmp_path):
    session = _make_session(tmp_path)
    assert fv.estimate_source_bytes(session, SegmentRange(2, 4)) == 3 * 2 * 1000


def test_success_moves_the_temp_file_into_place_and_reports_the_offset(tmp_path, monkeypatch):
    session = _make_session(tmp_path)
    folder = tmp_path / "games" / "k"

    def cut(sess, rng, out, **kw):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"video")
        return CutResult(segment_start=2, segment_end=5, duration_sec=12.0, source_incomplete=False)

    outcome = _run(session, folder, tmp_path, monkeypatch, cut=cut)

    assert outcome.error is None
    assert outcome.video.path == folder / "full.mp4"
    assert outcome.video.path.read_bytes() == b"video"
    assert outcome.video.size_bytes == 5
    assert outcome.video.offset_sec == 3.0
    assert not (folder / "full.tmp.mp4").exists()


def test_not_enough_space_skips_the_cut_and_says_why(tmp_path, monkeypatch):
    session = _make_session(tmp_path)
    called = []
    outcome = _run(session, tmp_path / "g", tmp_path, monkeypatch, cut=lambda *a, **k: called.append(1), free=100)
    assert outcome.video is None
    assert "저장 공간이 부족" in outcome.error
    assert called == []


def test_cut_failure_is_reported_not_raised_and_leaves_no_partial_file(tmp_path, monkeypatch):
    session = _make_session(tmp_path)
    folder = tmp_path / "g"

    def cut(sess, rng, out, **kw):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"half")
        raise subprocess.CalledProcessError(1, "ffmpeg", stderr=b"No space left on device")

    outcome = _run(session, folder, tmp_path, monkeypatch, cut=cut)

    assert outcome.video is None
    assert "저장 공간이 부족" in outcome.error
    assert list(folder.iterdir()) == []


def test_missing_segments_are_reported_not_raised(tmp_path, monkeypatch):
    session = _make_session(tmp_path)

    def cut(*a, **k):
        raise ClipCutError("세그먼트를 찾을 수 없다: 2-5")

    outcome = _run(session, tmp_path / "g", tmp_path, monkeypatch, cut=cut)
    assert outcome.video is None and "세그먼트" in outcome.error


def _cut_range(session, folder, tmp_path, monkeypatch, rng, cut):
    monkeypatch.setattr(fv, "cut_clip", cut)
    monkeypatch.setattr(fv, "_free_bytes", lambda f: 10 * 2**30)
    return fv.cut_full_video(
        session, rng, START, START + timedelta(seconds=rng.last * 3), folder,
        ffmpeg_path=Path("ffmpeg"), include_audio=True, tmp_dir=tmp_path,
    )


def test_missing_segments_after_the_recording_stopped_say_steam_stopped_recording(tmp_path, monkeypatch):
    from lumia_briefing_room.pipeline.recording_stop import STOPPED_BEFORE_MESSAGE

    session = _make_session(tmp_path)
    (session.directory / "chunk-stream0-00099.m4s").unlink()

    def cut(*a, **k):
        raise ClipCutError("세그먼트를 찾을 수 없다: 200-300")

    outcome = _cut_range(session, tmp_path / "g", tmp_path, monkeypatch, SegmentRange(200, 300), cut)
    assert outcome.video is None
    assert outcome.error == STOPPED_BEFORE_MESSAGE
    assert outcome.recording_stopped == "before"


def test_full_video_cut_short_by_a_stopped_recording_is_flagged(tmp_path, monkeypatch):
    session = _make_session(tmp_path)
    (session.directory / "chunk-stream0-00099.m4s").unlink()

    def cut(sess, rng, out, **kw):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"video")
        return CutResult(segment_start=2, segment_end=6, duration_sec=15.0, source_incomplete=True)

    outcome = _cut_range(session, tmp_path / "g", tmp_path, monkeypatch, SegmentRange(2, 60), cut)
    assert outcome.video is not None and outcome.error is None
    assert outcome.recording_stopped == "during"
