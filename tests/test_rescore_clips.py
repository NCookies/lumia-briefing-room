import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from rescore_clips import rescore_folder, rescore_meta  # noqa: E402

WEIGHTS = {"enemyRings": 0.7, "death": 0.9, "teammateDeath": 0.8}


def meta(**kw):
    base = {
        "tags": ["no_result"], "killDelta": 0, "assistDelta": 0, "died": False,
        "enemyRingMean": None, "pvpScore": 0.0, "pvpSignals": [],
    }
    base.update(kw)
    return base


def test_rescore_recomputes_score_and_signals_from_stored_evidence():
    result = rescore_meta(meta(tags=["death", "teammate_death"], died=True, pvpScore=1.0), WEIGHTS)

    assert result["pvpScore"] == 0.9
    assert result["pvpSignals"] == ["death", "teammate_death"]


def test_rescore_uses_the_ring_mean_when_no_other_evidence():
    result = rescore_meta(meta(enemyRingMean=0.75), WEIGHTS)

    assert result["pvpScore"] == 0.35
    assert result["pvpSignals"] == ["enemy_rings"]


def test_rescore_drops_no_result_when_another_tag_is_present():
    result = rescore_meta(meta(tags=["assist", "no_result"], assistDelta=1), WEIGHTS)

    assert result["tags"] == ["assist"]
    assert result["pvpScore"] == 1.0


def test_rescore_keeps_user_labels_and_unrelated_fields():
    result = rescore_meta(meta(userLabel="pvp", title="낮 교전", pinned=True), WEIGHTS)

    assert result["userLabel"] == "pvp"
    assert result["title"] == "낮 교전"
    assert result["pinned"] is True


def test_rescore_folder_rewrites_every_json_and_reports_changes(tmp_path):
    (tmp_path / "a.json").write_text(
        json.dumps(meta(tags=["teammate_death"], enemyRingMean=None, pvpScore=1.0)), encoding="utf-8"
    )
    (tmp_path / "b.json").write_text(json.dumps(meta()), encoding="utf-8")

    changed = rescore_folder(tmp_path, WEIGHTS)

    assert changed == 1
    assert json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))["pvpScore"] == 0.8
    assert json.loads((tmp_path / "b.json").read_text(encoding="utf-8"))["pvpScore"] == 0.0
