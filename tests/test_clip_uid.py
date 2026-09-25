import json
import re

from lumia_briefing_room.pipeline.clip_uid import (
    backfill_clip_uids,
    ensure_clip_uid,
    new_clip_uid,
    piece_uids,
)

HEX = re.compile(r"[0-9a-f]{32}")


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_new_uid_is_32_hex_without_hyphens_and_unique():
    a, b = new_clip_uid(), new_clip_uid()
    assert HEX.fullmatch(a) and "-" not in a
    assert a != b


def test_piece_uids_append_a_number_to_the_parent_uid_starting_at_one():
    parent = "a" * 32
    assert piece_uids(parent, set(), 3) == [f"{parent}-1", f"{parent}-2", f"{parent}-3"]


def test_piece_numbers_continue_after_the_highest_existing_direct_child():
    parent = "a" * 32
    existing = {f"{parent}-1", f"{parent}-4", f"{parent}-4-2", "b" * 32 + "-9"}
    assert piece_uids(parent, existing, 2) == [f"{parent}-5", f"{parent}-6"]


def test_pieces_of_a_piece_add_one_more_level():
    parent = "a" * 32 + "-1"
    assert piece_uids(parent, {parent + "-3"}, 1) == [parent + "-4"]


def test_ensure_adds_a_uid_once_and_keeps_every_other_field(tmp_path):
    meta = tmp_path / "20260920_134809_03.json"
    write(meta, {"title": "한글 제목", "userLabel": "pvp", "durationSec": 12.5})
    uid = ensure_clip_uid(meta)
    assert HEX.fullmatch(uid)
    assert read(meta) == {"title": "한글 제목", "userLabel": "pvp", "durationSec": 12.5, "clipUid": uid}
    assert ensure_clip_uid(meta) == uid
    assert list(tmp_path.glob("*.tmp")) == []


def test_ensure_returns_an_existing_uid_without_rewriting_the_file(tmp_path):
    meta = tmp_path / "c.json"
    write(meta, {"clipUid": "x" * 32})
    before = meta.stat().st_mtime_ns
    assert ensure_clip_uid(meta) == "x" * 32
    assert meta.stat().st_mtime_ns == before


def test_backfill_fills_live_trash_and_archive_and_is_idempotent(tmp_path):
    write(tmp_path / "c1.json", {"durationSec": 5, "userLabel": "pvp"})
    write(tmp_path / "c2.json", {"durationSec": 5})
    write(tmp_path / ".trash" / "c3.json", {"durationSec": 5})
    write(tmp_path / ".labels" / "gone.json", {"id": "gone", "userLabel": "pve"})
    assert backfill_clip_uids(tmp_path) == 4
    uids = [read(p)["clipUid"] for p in (tmp_path / "c1.json", tmp_path / "c2.json", tmp_path / ".trash" / "c3.json", tmp_path / ".labels" / "gone.json")]
    assert len(set(uids)) == 4
    assert backfill_clip_uids(tmp_path) == 0
    assert read(tmp_path / "c1.json")["clipUid"] == uids[0]


def test_archive_copy_of_a_surviving_clip_shares_that_clips_uid(tmp_path):
    write(tmp_path / "c1.json", {"durationSec": 5, "userLabel": "pvp"})
    write(tmp_path / ".labels" / "c1.json", {"id": "c1", "userLabel": "pvp"})
    backfill_clip_uids(tmp_path)
    assert read(tmp_path / ".labels" / "c1.json")["clipUid"] == read(tmp_path / "c1.json")["clipUid"]


def test_backfill_skips_game_records_and_non_clip_json(tmp_path):
    write(tmp_path / ".games" / "g.json", {"id": "g", "matchStartUtc": "2026-09-20T00:00:00Z"})
    write(tmp_path / "notes.json", ["not", "a", "clip"])
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    assert backfill_clip_uids(tmp_path) == 0
    assert "clipUid" not in read(tmp_path / ".games" / "g.json")


def test_backfill_survives_a_missing_folder(tmp_path):
    assert backfill_clip_uids(tmp_path / "nope") == 0
