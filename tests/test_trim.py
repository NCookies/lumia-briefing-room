import json
import re
import subprocess
from pathlib import Path

import pytest

from lumia_briefing_room.config import ThumbnailConfig
from lumia_briefing_room.pipeline.trim import trim_clip, validate_range

from conftest import FFMPEG_PATH, requires_ffmpeg


def make_video(path: Path, seconds: int = 20) -> None:
    subprocess.run(
        [
            str(FFMPEG_PATH), "-hide_banner", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=size=320x180:rate=30:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-c:v", "libx264", "-g", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )


def video_seconds(path: Path) -> float:
    """편집 리스트를 적용해 실제로 보이는 프레임 수로 잰다(OpenCV 프레임 수는 숨은 프리롤을 셈한다)."""
    out = subprocess.run(
        [str(FFMPEG_PATH), "-hide_banner", "-i", str(path), "-map", "0:v", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    frames = int(re.findall(r"frame=\s*(\d+)", out)[-1])
    return frames / 30.0


def write_clip(tmp_path: Path, seconds: int = 20, **meta) -> Path:
    mp4 = tmp_path / "clip1.mp4"
    make_video(mp4, seconds)
    thumb = tmp_path / ".thumbs" / "clip1.jpg"
    thumb.parent.mkdir()
    thumb.write_bytes(b"old thumbnail")
    data = {
        "title": "t", "durationSec": float(seconds), "videoOffsetSec": 100.0,
        "thumbnailPath": str(thumb), "userLabel": "pvp", **meta,
    }
    meta_path = tmp_path / "clip1.json"
    meta_path.write_text(json.dumps(data), encoding="utf-8")
    return meta_path


def test_validate_range_accepts_a_range_inside_the_clip():
    validate_range(2.0, 10.0, 20.0)
    validate_range(0.0, 20.0, 20.0)


@pytest.mark.parametrize(
    "start,end",
    [(-1.0, 5.0), (5.0, 5.0), (8.0, 4.0), (0.0, 25.0), (3.0, 3.5)],
)
def test_validate_range_rejects_bad_ranges(start, end):
    with pytest.raises(ValueError):
        validate_range(start, end, 20.0)


@requires_ffmpeg
def test_trim_keeps_only_the_selected_range_and_updates_metadata(tmp_path):
    meta_path = write_clip(tmp_path)

    meta = trim_clip(meta_path, 5.5, 12.5, ffmpeg_path=FFMPEG_PATH, thumbnail=ThumbnailConfig())

    assert video_seconds(tmp_path / "clip1.mp4") == pytest.approx(7.0, abs=0.2)
    assert meta["durationSec"] == pytest.approx(7.0)
    assert meta["videoOffsetSec"] == pytest.approx(105.5)
    assert meta["trimmed"] is True and meta["originalDurationSec"] == 20.0
    assert meta["userLabel"] == "pvp"
    assert json.loads(meta_path.read_text(encoding="utf-8")) == meta
    assert (tmp_path / ".thumbs" / "clip1.jpg").read_bytes() != b"old thumbnail"
    assert not list(tmp_path.glob("*.trim.mp4"))


@requires_ffmpeg
def test_trimming_twice_keeps_the_first_original_duration(tmp_path):
    meta_path = write_clip(tmp_path)

    trim_clip(meta_path, 2.0, 16.0, ffmpeg_path=FFMPEG_PATH, thumbnail=ThumbnailConfig())
    meta = trim_clip(meta_path, 3.0, 9.0, ffmpeg_path=FFMPEG_PATH, thumbnail=ThumbnailConfig())

    assert meta["originalDurationSec"] == 20.0
    assert meta["durationSec"] == pytest.approx(6.0)
    assert meta["videoOffsetSec"] == pytest.approx(105.0)
    assert video_seconds(tmp_path / "clip1.mp4") == pytest.approx(6.0, abs=0.2)


@requires_ffmpeg
def test_failed_trim_leaves_the_original_untouched(tmp_path):
    meta_path = write_clip(tmp_path)
    before = (tmp_path / "clip1.mp4").read_bytes()

    with pytest.raises(OSError):
        trim_clip(meta_path, 2.0, 9.0, ffmpeg_path=tmp_path / "no-such-ffmpeg.exe", thumbnail=ThumbnailConfig())

    assert (tmp_path / "clip1.mp4").read_bytes() == before
    assert "trimmed" not in json.loads(meta_path.read_text(encoding="utf-8"))
    assert not list(tmp_path.glob("*.trim.mp4"))


def test_validate_ranges_rejects_overlaps_and_sorts():
    from lumia_briefing_room.pipeline.trim import validate_ranges

    assert validate_ranges([(10.0, 15.0), (0.0, 5.0)], 20.0) == [(0.0, 5.0), (10.0, 15.0)]
    assert validate_ranges([(0.0, 5.0), (5.0, 9.0)], 20.0) == [(0.0, 5.0), (5.0, 9.0)]
    with pytest.raises(ValueError):
        validate_ranges([(0.0, 6.0), (5.0, 9.0)], 20.0)
    with pytest.raises(ValueError):
        validate_ranges([], 20.0)
    with pytest.raises(ValueError):
        validate_ranges([(0.0, 5.0), (8.0, 8.2)], 20.0)


@requires_ffmpeg
def test_split_makes_one_new_clip_per_range_and_trashes_the_original(tmp_path):
    from lumia_briefing_room.pipeline.trim import split_clip

    meta_path = write_clip(tmp_path, matchStartUtc="2026-01-01T00:00:00Z", tags=["x"], pvpScore=0.8, labelSource="user", labelNote="메모")
    trash = tmp_path / ".trash"

    new_paths = split_clip(
        meta_path, [(2.0, 6.0), (10.0, 15.0)], trash_dir=trash, ffmpeg_path=FFMPEG_PATH, thumbnail=ThumbnailConfig()
    )

    assert [p.stem for p in new_paths] == ["clip1-p1", "clip1-p2"]
    metas = [json.loads(p.read_text(encoding="utf-8")) for p in new_paths]
    assert [m["durationSec"] for m in metas] == [pytest.approx(4.0), pytest.approx(5.0)]
    assert [m["videoOffsetSec"] for m in metas] == [pytest.approx(102.0), pytest.approx(110.0)]
    for m, p in zip(metas, new_paths):
        assert m["splitFrom"] == "clip1" and m["trimmed"] is True and m["originalDurationSec"] == 20.0
        assert m["userLabel"] is None and "labelNote" not in m and m["pvpScore"] == 0.8 and m["tags"] == ["x"]
        assert m["matchStartUtc"] == "2026-01-01T00:00:00Z"
        assert (tmp_path / m["thumbnailPath"]).exists()
        assert p.with_suffix(".mp4").exists()
    assert video_seconds(new_paths[1].with_suffix(".mp4")) == pytest.approx(5.0, abs=0.2)
    assert not meta_path.exists() and (trash / "clip1.json").exists() and (trash / "clip1.mp4").exists()


@requires_ffmpeg
def test_failed_split_removes_new_pieces_and_keeps_the_original(tmp_path):
    from lumia_briefing_room.pipeline.trim import split_clip

    meta_path = write_clip(tmp_path)

    with pytest.raises(OSError):
        split_clip(
            meta_path, [(2.0, 6.0), (10.0, 15.0)], trash_dir=tmp_path / ".trash",
            ffmpeg_path=tmp_path / "no-such-ffmpeg.exe", thumbnail=ThumbnailConfig(),
        )

    assert meta_path.exists() and (tmp_path / "clip1.mp4").exists()
    assert sorted(p.name for p in tmp_path.glob("clip1-p*")) == []
    assert not (tmp_path / ".trash").exists()


@requires_ffmpeg
def test_split_avoids_existing_ids(tmp_path):
    from lumia_briefing_room.pipeline.trim import split_clip

    meta_path = write_clip(tmp_path)
    (tmp_path / "clip1-p1.json").write_text("{}", encoding="utf-8")

    new_paths = split_clip(
        meta_path, [(0.0, 4.0), (6.0, 10.0)], trash_dir=tmp_path / ".trash", ffmpeg_path=FFMPEG_PATH,
        thumbnail=ThumbnailConfig(),
    )

    assert [p.stem for p in new_paths] == ["clip1-p2", "clip1-p3"]


@requires_ffmpeg
def test_split_pieces_get_uids_derived_from_the_original_and_original_keeps_its_own(tmp_path):
    from lumia_briefing_room.pipeline.trim import split_clip

    parent = "a" * 32
    meta_path = write_clip(tmp_path, clipUid=parent)

    new_paths = split_clip(
        meta_path, [(0.0, 4.0), (6.0, 10.0)], trash_dir=tmp_path / ".trash", ffmpeg_path=FFMPEG_PATH,
        thumbnail=ThumbnailConfig(),
    )

    uids = [json.loads(p.read_text(encoding="utf-8"))["clipUid"] for p in new_paths]
    assert uids == [f"{parent}-1", f"{parent}-2"]
    assert json.loads((tmp_path / ".trash" / "clip1.json").read_text(encoding="utf-8"))["clipUid"] == parent


@requires_ffmpeg
def test_split_gives_an_original_without_uid_one_and_continues_after_existing_pieces(tmp_path):
    from lumia_briefing_room.pipeline.trim import split_clip

    meta_path = write_clip(tmp_path)
    original_uid = "b" * 32
    (tmp_path / ".trash").mkdir()
    (tmp_path / ".trash" / "old.json").write_text(json.dumps({"clipUid": f"{original_uid}-1"}), encoding="utf-8")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["clipUid"] = original_uid
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    (tmp_path / ".labels").mkdir()
    (tmp_path / ".labels" / "gone.json").write_text(json.dumps({"clipUid": f"{original_uid}-3"}), encoding="utf-8")

    new_paths = split_clip(
        meta_path, [(0.0, 4.0), (6.0, 10.0)], trash_dir=tmp_path / ".trash", ffmpeg_path=FFMPEG_PATH,
        thumbnail=ThumbnailConfig(),
    )

    uids = [json.loads(p.read_text(encoding="utf-8"))["clipUid"] for p in new_paths]
    assert uids == [f"{original_uid}-4", f"{original_uid}-5"]


@requires_ffmpeg
def test_splitting_a_piece_appends_another_level(tmp_path):
    from lumia_briefing_room.pipeline.trim import split_clip

    parent = "c" * 32 + "-2"
    meta_path = write_clip(tmp_path, clipUid=parent)
    new_paths = split_clip(
        meta_path, [(0.0, 4.0)], trash_dir=tmp_path / ".trash", ffmpeg_path=FFMPEG_PATH, thumbnail=ThumbnailConfig(),
    )
    assert json.loads(new_paths[0].read_text(encoding="utf-8"))["clipUid"] == parent + "-1"


@requires_ffmpeg
def test_single_range_trim_keeps_the_clip_uid(tmp_path):
    meta_path = write_clip(tmp_path, clipUid="d" * 32)
    meta = trim_clip(meta_path, 2.0, 8.0, ffmpeg_path=FFMPEG_PATH, thumbnail=ThumbnailConfig())
    assert meta["clipUid"] == "d" * 32
