import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from migrate_labels import migrate_folder, migrate_label  # noqa: E402

SESSION = "bg_1049590_20260920_120101"


def clip(cid, start, dur, label=None, session=SESSION, **kw):
    return {"id": cid, "sessionDir": session, "videoOffsetSec": start, "durationSec": dur, "userLabel": label, **kw}


def test_no_overlapping_labeled_clip_leaves_the_label_empty():
    assert migrate_label(clip("n", 100, 50), [clip("o", 300, 40, "pvp")]) == (None, False, [])


def test_single_overlap_carries_its_label():
    assert migrate_label(clip("n", 100, 50), [clip("o", 90, 30, "pve")]) == ("pve", False, ["o"])


def test_pvp_wins_when_the_new_clip_contains_a_pvp_fight():
    label, conflict, sources = migrate_label(
        clip("n", 3114, 81), [clip("o1", 3114, 24, "pve"), clip("o2", 3186, 9, "pvp")]
    )

    assert label == "pvp"
    assert conflict is True
    assert sources == ["o1", "o2"]


def test_agreeing_labels_are_not_a_conflict():
    assert migrate_label(clip("n", 0, 100), [clip("a", 0, 30, "pvp"), clip("b", 40, 30, "pvp")])[1] is False


def test_tiny_overlaps_are_ignored():
    assert migrate_label(clip("n", 100, 50), [clip("o", 148, 30, "pvp")]) == (None, False, [])


def test_other_sessions_never_match():
    assert migrate_label(clip("n", 100, 50), [clip("o", 100, 50, "pvp", session="bg_1_20260101_000000")])[0] is None


def test_unlabeled_old_clips_are_ignored():
    assert migrate_label(clip("n", 100, 50), [clip("o", 100, 50, None)]) == (None, False, [])


def test_a_human_label_beats_a_carried_over_one():
    label, conflict, sources = migrate_label(
        clip("n", 100, 20),
        [clip("big", 60, 264, "pvp", labelSource="migrated"), clip("small", 100, 20, "pve", labelSource="user")],
    )

    assert (label, conflict, sources) == ("pve", False, ["small"])


def test_a_carried_over_pvp_from_a_much_bigger_clip_is_not_inherited_by_a_signal_free_clip():
    # 옛 통짜 클립(264초)이 pvp 였다고 그 안의 무신호(점수 0) 짧은 클립까지 pvp 가 되면 안 된다.
    new = clip("n", 9427, 24, pvpScore=0.0)
    big = clip("big", 9402, 264, "pvp", labelSource="migrated")

    assert migrate_label(new, [big]) == (None, False, [])


def test_a_carried_over_pvp_is_inherited_when_the_new_clip_has_signals():
    new = clip("n", 9463, 90, pvpScore=1.0)
    big = clip("big", 9402, 264, "pvp", labelSource="migrated")

    assert migrate_label(new, [big])[0] == "pvp"


def test_a_carried_over_pvp_is_inherited_when_the_old_clip_is_about_the_same_size():
    new = clip("n", 100, 24, pvpScore=0.0)
    old = clip("o", 100, 24, "pvp", labelSource="migrated")

    assert migrate_label(new, [old])[0] == "pvp"


def test_a_user_pvp_from_a_bigger_clip_is_still_inherited_by_a_signal_free_clip():
    new = clip("n", 100, 24, pvpScore=0.0)
    old = clip("o", 90, 200, "pvp", labelSource="user")

    assert migrate_label(new, [old])[0] == "pvp"


def _write(folder, cid, **meta):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{cid}.json").write_text(json.dumps({**meta}), encoding="utf-8")


def test_migrate_folder_writes_label_source_and_conflict(tmp_path):
    _write(tmp_path / "old", "o1", sessionDir=SESSION, videoOffsetSec=0, durationSec=30, userLabel="pve")
    _write(tmp_path / "old", "o2", sessionDir=SESSION, videoOffsetSec=40, durationSec=30, userLabel="pvp")
    _write(tmp_path / "new", "n1", sessionDir=SESSION, videoOffsetSec=0, durationSec=80, userLabel=None)

    report = migrate_folder(tmp_path / "old", tmp_path / "new")

    saved = json.loads((tmp_path / "new" / "n1.json").read_text(encoding="utf-8"))
    assert saved["userLabel"] == "pvp"
    assert saved["labelSource"] == "migrated"
    assert saved["labelConflict"] is True
    assert report == {"migrated": 1, "conflicts": 1, "skipped_user_labeled": 0, "unlabeled": 0}


def test_migrate_folder_never_overwrites_a_label_the_user_already_set(tmp_path):
    _write(tmp_path / "old", "o1", sessionDir=SESSION, videoOffsetSec=0, durationSec=30, userLabel="pvp")
    _write(tmp_path / "new", "n1", sessionDir=SESSION, videoOffsetSec=0, durationSec=30, userLabel="pve", labelSource="user")

    report = migrate_folder(tmp_path / "old", tmp_path / "new")

    saved = json.loads((tmp_path / "new" / "n1.json").read_text(encoding="utf-8"))
    assert saved["userLabel"] == "pve"
    assert report["skipped_user_labeled"] == 1


def test_migrate_folder_counts_new_clips_with_nothing_to_carry(tmp_path):
    _write(tmp_path / "old", "o1", sessionDir=SESSION, videoOffsetSec=500, durationSec=30, userLabel="pvp")
    _write(tmp_path / "new", "n1", sessionDir=SESSION, videoOffsetSec=0, durationSec=30, userLabel=None)

    assert migrate_folder(tmp_path / "old", tmp_path / "new")["unlabeled"] == 1


def test_vod_clips_are_matched_by_vod_id_and_never_across_vods():
    def vclip(cid, start, dur, label=None, vod="aaa"):
        return {"id": cid, "vodId": vod, "videoOffsetSec": start, "durationSec": dur, "userLabel": label}

    assert migrate_label(vclip("n", 100, 50), [vclip("o", 90, 30, "pvp")]) == ("pvp", False, ["o"])
    assert migrate_label(vclip("n", 100, 50), [vclip("o", 90, 30, "pvp", vod="bbb")]) == (None, False, [])


def test_a_steam_clip_never_matches_a_vod_clip():
    steam = clip("s", 100, 50, "pvp")
    vod = {"id": "v", "vodId": "aaa", "videoOffsetSec": 100, "durationSec": 50, "userLabel": None}

    assert migrate_label(vod, [steam]) == (None, False, [])
