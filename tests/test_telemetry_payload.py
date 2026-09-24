import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from lumia_briefing_room.telemetry.payload import (
    SENT_FIELDS,
    build_label,
    display_id,
    hash_key,
    label_digest,
    normalize_label_value,
)

CONTRACT = Path(__file__).resolve().parent / "contract"
SCHEMA = json.loads((CONTRACT / "receiver.schema.json").read_text(encoding="utf-8"))
FIELDS = json.loads((CONTRACT / "app-metadata-fields.json").read_text(encoding="utf-8"))
INSTALL = "3f2b8c1e-5a4d-4e6f-9b7a-1c2d3e4f5a6b"


def label_validator():
    return Draft202012Validator({"$ref": "#/$defs/Label", "$defs": SCHEMA["$defs"]})


def steam_meta(**over):
    meta = {
        "title": "2일차 밤 학교 교전", "sessionDir": "bg_1049590_20260920_120101",
        "sessionStartUtc": "2026-09-20T12:01:01Z", "matchStartUtc": "2026-09-20T12:05:30.781000Z",
        "gameMode": "battle_royale", "sourceWidth": 2560, "sourceHeight": 1440, "segmentStart": 245,
        "segmentEnd": 253, "videoOffsetSec": 733.0, "durationSec": 27.0,
        "thumbnailPath": "C:\\Users\\someone\\Videos\\clips\\.thumbs\\x.jpg", "sourceIncomplete": False,
        "audioStatus": "full", "combatStartOffsetSec": 738.0, "combatEndOffsetSec": 750.0,
        "prerollSource": "combat", "tags": ["kill"], "killDelta": 1, "assistDelta": 0, "died": False,
        "pvpScore": 0.8, "pvpSignals": ["kill_delta"], "teamWipe": None, "enemyRingMean": 0.12,
        "ultimateDelta": 1, "region": "학교", "userLabel": "pvp", "labelSource": "user", "labelConflict": False,
        "labelNote": "3인 교전", "gameDay": 2, "dayNight": "night", "phaseIndex": 3, "reviveCost": "free",
        "myCharacter": "아야", "teamCharacters": ["리오"], "pinned": True, "deletedAt": None,
        "matchKills": 3, "matchAssists": 4, "matchTeamKills": None, "detectorConfidence": 1.0,
        "matchResult": {"nickname": "내닉네임", "imagePath": "C:\\x.jpg"}, "matchEndUtc": "2026-09-20T12:20:00Z",
    }
    meta.update(over)
    return meta


def vod_meta(**over):
    meta = steam_meta(source="vod", vodId="3fa91c02b7de", vodFile="H:/vod/a.mp4", streamer="스트리머",
                      vodGameIndex=3, gameStartOffsetSec=90.0, gameEndOffsetSec=900.0)
    for gone in ("sessionDir", "sessionStartUtc", "matchStartUtc", "segmentStart", "segmentEnd", "matchEndUtc"):
        meta.pop(gone)
    meta.update(over)
    return meta


def build(meta, clip_id="20260920_120530_01"):
    return build_label(meta, clip_id=clip_id, install_id=INSTALL)


def test_maps_local_labels_to_the_neutral_wire_values():
    assert build(steam_meta(userLabel="pvp"))["userLabel"] == "combat"
    assert build(steam_meta(userLabel="pve"))["userLabel"] == "other"


@pytest.mark.parametrize("value", [None, "", "none", "hunt", 1])
def test_unlabeled_or_unknown_labels_are_not_sent(value):
    assert build(steam_meta(userLabel=value)) is None


def test_label_matches_the_contract_schema_for_steam_and_vod_clips():
    for meta in (steam_meta(), vod_meta(), steam_meta(userLabel="pve", labelNote=None)):
        label = build(meta, clip_id="vod_x" if meta.get("source") == "vod" else "20260920_120530_01")
        assert not list(label_validator().iter_errors(label)), label


def test_never_sends_private_fields():
    label = build(steam_meta())
    blob = json.dumps(label, ensure_ascii=False)
    for secret in ("2일차 밤 학교 교전", "bg_1049590", "C:\\\\Users", "someone", "리오", "내닉네임", "2026-09-20T12:05"):
        assert secret not in blob
    for key in ("title", "sessionDir", "thumbnailPath", "teamCharacters", "matchResult", "pinned", "deletedAt",
                "matchStartUtc", "videoOffsetSec"):
        assert key not in label


def test_vod_clip_is_marked_and_keeps_out_streamer_and_file():
    label = build(vod_meta(), clip_id="vod_3fa91c02b7de_g03_000095")
    blob = json.dumps(label, ensure_ascii=False)
    assert label["source"] == "vod"
    assert "스트리머" not in blob and "a.mp4" not in blob and "3fa91c02b7de" not in blob
    assert build(steam_meta())["source"] == "recording"


def test_keys_are_hashes_salted_by_install_id_and_stable():
    a = build(steam_meta())
    assert a["matchKey"] == build(steam_meta())["matchKey"]
    assert len(a["matchKey"]) == 32 and len(a["clipKey"]) == 32
    other = build_label(steam_meta(), clip_id="20260920_120530_01", install_id="00000000-0000-4000-8000-000000000000")
    assert other["matchKey"] != a["matchKey"] and other["clipKey"] != a["clipKey"]


def test_clips_of_one_game_share_a_match_key_but_not_a_clip_key():
    first = build(steam_meta(), clip_id="20260920_120530_01")
    second = build(steam_meta(), clip_id="20260920_120530_02")
    assert first["matchKey"] == second["matchKey"] and first["clipKey"] != second["clipKey"]


def test_vod_games_get_their_own_match_key():
    a = build(vod_meta(vodGameIndex=1), clip_id="vod_a")
    b = build(vod_meta(vodGameIndex=2), clip_id="vod_b")
    assert a["matchKey"] != b["matchKey"]


def test_old_clips_without_session_info_still_get_a_valid_match_key():
    label = build(steam_meta(sessionDir=None, matchStartUtc=None))
    assert not list(label_validator().iter_errors(label))


def test_none_values_are_dropped_and_wrongly_typed_values_are_skipped():
    label = build(steam_meta(killDelta="many", region=None, pvpScore=7, sourceWidth=True))
    assert "killDelta" not in label and "region" not in label
    assert "pvpScore" not in label and "sourceWidth" not in label
    assert not list(label_validator().iter_errors(label))


def test_long_values_are_trimmed_to_the_contract_limits():
    label = build(steam_meta(region="x" * 200, tags=[f"t{i}" for i in range(50)], labelNote="가" * 900,
                             pvpSignals=["s" * 100]))
    assert len(label["region"]) == 64 and len(label["tags"]) == 32 and len(label["labelNote"]) == 500
    assert len(label["pvpSignals"][0]) == 64
    assert not list(label_validator().iter_errors(label))


def test_label_note_is_stripped_and_empty_notes_are_omitted():
    assert build(steam_meta(labelNote="  메모  "))["labelNote"] == "메모"
    assert "labelNote" not in build(steam_meta(labelNote="   "))


def test_digest_changes_only_when_the_sent_content_changes():
    base = label_digest(build(steam_meta()))
    assert label_digest(build(steam_meta(title="바꾼 제목", pinned=False))) == base
    assert label_digest(build(steam_meta(userLabel="pve"))) != base
    assert label_digest(build(steam_meta(labelNote="다른 메모"))) != base


def test_sent_fields_are_exactly_the_contract_manifest():
    assert set(SENT_FIELDS) == set(FIELDS["sent"])


def test_display_id_has_the_contract_shape_and_is_stable():
    shown = display_id(INSTALL)
    assert shown == display_id(INSTALL) and shown != display_id("00000000-0000-4000-8000-000000000000")
    import re

    assert re.fullmatch(r"LUMIA-[0-9A-Z]{4}-[0-9A-Z]{4}", shown)


def test_hash_key_is_32_hex():
    assert len(hash_key("a", "b")) == 32 and hash_key("a", "b") != hash_key("ab")


def test_normalize_label_value():
    assert normalize_label_value("pvp") == "combat" and normalize_label_value("pve") == "other"
    assert normalize_label_value(None) is None
