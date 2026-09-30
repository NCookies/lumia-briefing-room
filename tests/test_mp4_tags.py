import struct
import subprocess
from pathlib import Path

import pytest

from lumia_briefing_room.pipeline import mp4_tags

from conftest import FFMPEG_PATH, requires_ffmpeg


def box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def data_box(text: str) -> bytes:
    return box(b"data", struct.pack(">II", 1, 0) + text.encode("utf-8"))


def mp4_with_comment(text: str, *, moov_first: bool = False, extra_items: bytes = b"") -> bytes:
    ilst = box(b"ilst", extra_items + box(b"\xa9cmt", data_box(text)))
    meta = box(b"meta", b"\x00\x00\x00\x00" + box(b"hdlr", b"\x00" * 25) + ilst)
    moov = box(b"moov", box(b"mvhd", b"\x00" * 100) + box(b"udta", meta))
    ftyp = box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41")
    mdat = box(b"mdat", b"\x00" * 5000)
    return ftyp + (moov + mdat if moov_first else mdat + moov)


def test_reads_the_uid_from_the_comment_tag_when_moov_is_at_the_end(tmp_path):
    p = tmp_path / "a.mp4"
    p.write_bytes(mp4_with_comment("lumia:clipUid=" + "ab" * 16))
    assert mp4_tags.read_clip_uid(p) == "ab" * 16


def test_reads_the_uid_when_moov_is_at_the_start(tmp_path):
    p = tmp_path / "a.mp4"
    p.write_bytes(mp4_with_comment("lumia:clipUid=abc-1-3", moov_first=True))
    assert mp4_tags.read_clip_uid(p) == "abc-1-3"


def test_other_comments_and_other_items_are_not_our_tag(tmp_path):
    p = tmp_path / "a.mp4"
    p.write_bytes(mp4_with_comment("촬영: 내 방송"))
    assert mp4_tags.read_clip_uid(p) is None
    name = box(b"\xa9nam", data_box("제목"))
    p.write_bytes(mp4_with_comment("lumia:clipUid=xyz", extra_items=name))
    assert mp4_tags.read_clip_uid(p) == "xyz"


def test_files_without_tags_or_broken_files_give_none(tmp_path):
    (tmp_path / "empty.mp4").write_bytes(b"")
    (tmp_path / "junk.mp4").write_bytes(b"not an mp4 at all" * 10)
    (tmp_path / "trunc.mp4").write_bytes(mp4_with_comment("lumia:clipUid=x")[:-30])
    plain = box(b"ftyp", b"isom" + b"\x00" * 8) + box(b"moov", box(b"mvhd", b"\x00" * 100)) + box(b"mdat", b"x")
    (tmp_path / "plain.mp4").write_bytes(plain)
    for name in ("empty", "junk", "trunc", "plain"):
        assert mp4_tags.read_clip_uid(tmp_path / f"{name}.mp4") is None
    assert mp4_tags.read_clip_uid(tmp_path / "missing.mp4") is None


def test_result_is_cached_until_the_file_changes(tmp_path, monkeypatch):
    p = tmp_path / "a.mp4"
    p.write_bytes(mp4_with_comment("lumia:clipUid=one"))
    assert mp4_tags.read_clip_uid(p) == "one"
    calls = []
    real = mp4_tags._parse_uid
    monkeypatch.setattr(mp4_tags, "_parse_uid", lambda path: (calls.append(1), real(path))[1])
    assert mp4_tags.read_clip_uid(p) == "one" and calls == []
    p.write_bytes(mp4_with_comment("lumia:clipUid=second"))
    assert mp4_tags.read_clip_uid(p) == "second" and calls == [1]


def test_ffmpeg_args_carry_the_tag():
    args = mp4_tags.uid_metadata_args("abc")
    assert args == ["-metadata", "comment=lumia:clipUid=abc"]


@requires_ffmpeg
def test_a_tag_written_by_real_ffmpeg_is_read_back_and_survives_copy_and_trim(tmp_path):
    src = tmp_path / "src.mp4"
    subprocess.run(
        [str(FFMPEG_PATH), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=6",
         "-c:v", "libx264", "-g", "10", str(src)], check=True,
    )
    tagged = tmp_path / "tagged.mp4"
    subprocess.run([str(FFMPEG_PATH), "-v", "error", "-y", "-i", str(src), "-c", "copy",
                    *mp4_tags.uid_metadata_args("uid123"), str(tagged)], check=True)
    assert mp4_tags.read_clip_uid(tagged) == "uid123"
    trimmed = tmp_path / "trimmed.mp4"
    subprocess.run([str(FFMPEG_PATH), "-v", "error", "-y", "-ss", "1", "-to", "4", "-i", str(tagged),
                    "-map", "0", "-c", "copy", str(trimmed)], check=True)
    assert mp4_tags.read_clip_uid(trimmed) == "uid123"
    renamed = tmp_path / "이름 바꿈.mp4"
    tagged.rename(renamed)
    assert mp4_tags.read_clip_uid(renamed) == "uid123"
