import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from eval_pvp import evaluate_labels, load_clips  # noqa: E402


def m(label, score, rings=None, signals=None):
    return {"userLabel": label, "pvpScore": score, "enemyRingMean": rings, "pvpSignals": signals or []}


def test_ignores_unlabeled_clips():
    report = evaluate_labels([m(None, 1.0), m("pvp", 1.0)])

    assert report["labeled"] == 1


def test_counts_labels_and_flags_confirmed_evidence_on_hunting_clips():
    report = evaluate_labels([m("pvp", 1.0), m("pve", 1.0, signals=["death"]), m("pve", 0.1)])

    assert report["pvp"] == 1 and report["pve"] == 2
    assert report["confirmed_but_pve"] == 1


def test_ring_stats_only_use_clips_without_confirmed_evidence():
    report = evaluate_labels(
        [
            m("pvp", 1.0, 5.0, ["kill_delta"]), m("pvp", 0.9, 4.0, ["death"]),
            m("pvp", 0.0, 1.2), m("pve", 0.0, 0.2), m("pve", 0.0, 0.4),
        ]
    )

    assert report["rings"]["pvp"]["mean"] == 1.2
    assert report["rings"]["pvp"]["n"] == 1
    assert report["rings"]["pve"]["mean"] == 0.3


def test_threshold_sweep_finds_a_clean_split():
    clips = [m("pvp", 1.0), m("pvp", 0.6), m("pve", 0.3), m("pve", 0.1)]

    report = evaluate_labels(clips)

    assert report["best"]["threshold"] == 0.6
    assert report["best"]["precision"] == 1.0
    assert report["best"]["recall"] == 1.0


def test_threshold_sweep_reports_the_tradeoff_when_scores_overlap():
    clips = [m("pvp", 0.9), m("pvp", 0.3), m("pve", 0.5), m("pve", 0.1)]

    best = evaluate_labels(clips)["best"]

    assert 0.0 < best["f1"] < 1.0


def test_empty_input_reports_nothing_labeled():
    report = evaluate_labels([])

    assert report["labeled"] == 0
    assert report["best"] is None


def test_load_clips_reads_every_json_in_a_folder(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"userLabel": "pvp"}), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps({"userLabel": None}), encoding="utf-8")

    assert len(load_clips(tmp_path)) == 2


def test_ring_auc_is_half_when_the_signal_does_not_separate_and_one_when_it_does():
    flat = evaluate_labels([m("pvp", 0.0, 0.4), m("pvp", 0.0, 0.2), m("pve", 0.0, 0.4), m("pve", 0.0, 0.2)])
    clean = evaluate_labels([m("pvp", 0.0, 1.0), m("pvp", 0.0, 0.9), m("pve", 0.0, 0.1), m("pve", 0.0, 0.2)])

    assert flat["ring_auc"] == 0.5
    assert clean["ring_auc"] == 1.0


def test_ring_auc_is_none_without_both_classes():
    assert evaluate_labels([m("pvp", 0.0, 0.4)])["ring_auc"] is None


def test_load_clips_also_reads_the_label_archive_but_a_live_clip_with_the_same_id_wins(tmp_path):
    (tmp_path / "live.json").write_text(json.dumps({"userLabel": "pve", "src": "live"}), encoding="utf-8")
    archive = tmp_path / ".labels"
    archive.mkdir()
    (archive / "live.json").write_text(json.dumps({"userLabel": "pvp", "src": "old"}), encoding="utf-8")
    (archive / "gone.json").write_text(json.dumps({"userLabel": "pvp", "src": "archive"}), encoding="utf-8")

    assert sorted(c["src"] for c in load_clips(tmp_path)) == ["archive", "live"]
