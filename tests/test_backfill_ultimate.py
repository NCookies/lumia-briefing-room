import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from backfill_ultimate import apply_ultimate_delta  # noqa: E402

WEIGHTS = {"death": 0.9, "teammateDeath": 0.8, "ultimateUsed": 0.6}


def meta(**kw):
    base = {
        "title": "낮 묘지 교전", "tags": ["no_result"], "killDelta": 0, "assistDelta": 0,
        "died": False, "enemyRingMean": None, "ultimateDelta": None,
        "pvpScore": 0.0, "pvpSignals": [], "userLabel": "pvp",
    }
    base.update(kw)
    return base


def test_apply_sets_the_delta_and_rescoes_when_it_clears_the_threshold():
    result = apply_ultimate_delta(meta(), 0.48, WEIGHTS)

    assert result["ultimateDelta"] == 0.48
    assert result["pvpScore"] == 0.6
    assert result["pvpSignals"] == ["ultimate_used"]


def test_apply_sets_the_delta_but_does_not_add_evidence_below_the_threshold():
    result = apply_ultimate_delta(meta(), 0.05, WEIGHTS)

    assert result["ultimateDelta"] == 0.05
    assert result["pvpScore"] == 0.0
    assert result["pvpSignals"] == []


def test_apply_keeps_stronger_existing_evidence_but_still_lists_the_new_signal():
    result = apply_ultimate_delta(meta(tags=["death"], died=True, pvpScore=0.9), 0.48, WEIGHTS)

    assert result["ultimateDelta"] == 0.48
    assert result["pvpScore"] == 0.9
    assert result["pvpSignals"] == ["death", "ultimate_used"]


def test_apply_does_nothing_when_the_delta_is_unknown():
    original = meta()

    assert apply_ultimate_delta(original, None, WEIGHTS) == original


def test_apply_keeps_user_labels_and_other_fields():
    result = apply_ultimate_delta(meta(pinned=True, userLabel="pve"), 0.48, WEIGHTS)

    assert result["userLabel"] == "pve"
    assert result["pinned"] is True
    assert result["title"] == "낮 묘지 교전"
