import json
from datetime import datetime, timezone

from lumia_briefing_room.config import RetentionConfig
from lumia_briefing_room.pipeline.cleanup import run_cleanup
from lumia_briefing_room.pipeline.game_records import (
    clear_records,
    delete_record,
    game_key,
    load_records,
    record_game,
    records_dir_for,
)
from lumia_briefing_room.pipeline.retention import purge_expired, trash_clip

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
RESULT = {
    "matchType": "rank", "matchLabel": "랭크", "placement": 3, "total": 8, "outcome": None,
    "nickname": "me", "character": "아야", "tk": 4, "kills": 2, "assists": 1,
    "teammates": [{"nickname": "a", "character": "쇼우"}],
}


def write_clip(root, clip_id, *, start="2026-09-01T10:00:00Z", result=True, image=True, **meta):
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{clip_id}.mp4").write_bytes(b"x" * 10)
    match_result = None
    if result:
        match_result = dict(RESULT)
        if image:
            img = root / ".thumbs" / "20260901_100000_result.jpg"
            img.parent.mkdir(exist_ok=True)
            img.write_bytes(b"result-jpg")
            match_result["imagePath"] = str(img)
    data = {
        "title": clip_id, "tags": ["kill"], "pinned": False, "deletedAt": None, "thumbnailPath": None,
        "sessionDir": "session_a", "matchStartUtc": start, "gameMode": "battle_royale",
        "matchResult": match_result, **meta,
    }
    (root / f"{clip_id}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return root / f"{clip_id}.json"


def test_game_key_is_filesystem_safe_and_stable():
    key = game_key("session_a", "2026-09-01T10:00:00Z")
    assert key == game_key("session_a", "2026-09-01T10:00:00Z")
    assert not set(key) & set('\\/:*?"<>| ')


def test_record_game_keeps_summary_and_copies_result_image(tmp_path):
    clips = tmp_path / "clips"
    meta = write_clip(clips, "a_01")
    records = records_dir_for(clips)

    record_game(meta, records)

    [rec] = load_records(records)
    assert rec["sessionDir"] == "session_a" and rec["matchStartUtc"] == "2026-09-01T10:00:00Z"
    assert rec["matchResult"]["placement"] == 3 and rec["matchResult"]["teammates"][0]["character"] == "쇼우"
    image = records / f"{rec['id']}.jpg"
    assert image.read_bytes() == b"result-jpg"
    assert rec["matchResult"]["imagePath"] == str(image)


def test_record_game_skips_clips_without_result(tmp_path):
    meta = write_clip(tmp_path / "clips", "a_01", result=False)
    assert record_game(meta, records_dir_for(tmp_path / "clips")) is None
    assert load_records(records_dir_for(tmp_path / "clips")) == []


def test_record_game_without_image_keeps_summary_only(tmp_path):
    clips = tmp_path / "clips"
    meta = write_clip(clips, "a_01", image=False)
    record_game(meta, records_dir_for(clips))
    [rec] = load_records(records_dir_for(clips))
    assert not rec["matchResult"].get("imagePath")


def test_two_clips_of_one_game_make_one_record(tmp_path):
    clips = tmp_path / "clips"
    records = records_dir_for(clips)
    record_game(write_clip(clips, "a_01"), records)
    record_game(write_clip(clips, "a_02"), records)
    assert len(load_records(records)) == 1


def test_delete_and_clear_records(tmp_path):
    clips = tmp_path / "clips"
    records = records_dir_for(clips)
    record_game(write_clip(clips, "a_01"), records)
    record_game(write_clip(clips, "b_01", start="2026-09-02T10:00:00Z"), records)
    first = load_records(records)[0]["id"]

    assert delete_record(records, first) is True
    assert not (records / f"{first}.jpg").exists()
    assert len(load_records(records)) == 1
    assert delete_record(records, "nope") is False

    clear_records(records)
    assert load_records(records) == []


def test_purge_expired_records_game_when_records_dir_given(tmp_path):
    clips = tmp_path / "clips"
    trash = clips / ".trash"
    meta = write_clip(clips, "a_01")
    trash_clip(meta, trash, now=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))

    purge_expired(trash, trash_days=30, now=lambda: NOW, records_dir=records_dir_for(clips))

    [rec] = load_records(records_dir_for(clips))
    assert rec["matchResult"]["placement"] == 3


def test_permanent_auto_delete_records_game(tmp_path):
    clips = tmp_path / "clips"
    write_clip(clips, "a_01", start="2026-01-01T10:00:00Z")
    cfg = RetentionConfig(auto_clean_enabled=True, max_age_days=30, delete_mode="permanent")

    run_cleanup(clips, clips / ".trash", cfg, now=NOW)

    assert not (clips / "a_01.json").exists()
    assert len(load_records(records_dir_for(clips))) == 1


def test_keep_game_records_off_skips_and_clears_records(tmp_path):
    clips = tmp_path / "clips"
    records = records_dir_for(clips)
    record_game(write_clip(clips, "old_game", start="2026-01-05T10:00:00Z"), records)
    write_clip(clips, "a_01", start="2026-01-01T10:00:00Z")
    cfg = RetentionConfig(
        auto_clean_enabled=True, max_age_days=30, delete_mode="permanent", keep_game_records=False
    )

    run_cleanup(clips, clips / ".trash", cfg, now=NOW)

    assert load_records(records) == []
