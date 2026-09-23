"""일회성 조사 도구: 라벨링 통계·분석 자료를 JSON으로 뽑는다 (대시보드용).

usage: label_stats.py <clips_dir> <out.json>
"""
import json
import os
import sys
from collections import Counter, defaultdict


def match_key(filename: str) -> str:
    parts = filename.split("_")
    return "_".join(parts[:2])


def bucket(value, edges):
    for i in range(len(edges) - 1):
        if edges[i] <= value < edges[i + 1]:
            return f"{edges[i]}-{edges[i+1]}"
    return f"{edges[-1]}+"


def main():
    clips_dir, out_path = sys.argv[1], sys.argv[2]
    files = sorted(f for f in os.listdir(clips_dir) if f.endswith(".json"))
    clips = []
    for f in files:
        with open(os.path.join(clips_dir, f), encoding="utf-8") as fh:
            d = json.load(fh)
        d["_file"] = f
        d["_match"] = match_key(f)
        clips.append(d)

    total = len(clips)
    labeled = [c for c in clips if c.get("userLabel") in ("pvp", "pve")]
    pvp = [c for c in clips if c.get("userLabel") == "pvp"]
    pve = [c for c in clips if c.get("userLabel") == "pve"]
    unlabeled = [c for c in clips if c.get("userLabel") not in ("pvp", "pve")]

    tag_counts = Counter()
    for c in clips:
        for t in c.get("tags", []):
            tag_counts[t] += 1

    signal_counts = Counter()
    for c in clips:
        for s in c.get("pvpSignals", []) or []:
            signal_counts[s] += 1

    def score_hist(group):
        edges = [0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.01]
        labels = ["0", "0~0.3", "0.3~0.5", "0.5~0.7", "0.7~0.9", "0.9~1.0"]
        counts = [0] * len(labels)
        for c in group:
            s = c.get("pvpScore") or 0.0
            if s == 0:
                counts[0] += 1
            else:
                for i in range(len(edges) - 1):
                    if edges[i] <= s < edges[i + 1]:
                        counts[i] += 1 if i > 0 else 0
                        break
        # simpler manual binning
        counts = [0, 0, 0, 0, 0, 0]
        for c in group:
            s = c.get("pvpScore") or 0.0
            if s <= 0.0:
                counts[0] += 1
            elif s < 0.3:
                counts[1] += 1
            elif s < 0.5:
                counts[2] += 1
            elif s < 0.7:
                counts[3] += 1
            elif s < 0.9:
                counts[4] += 1
            else:
                counts[5] += 1
        return {"labels": labels, "counts": counts}

    def ultimate_delta_hist(group):
        edges = [0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 1.01]
        labels = ["0~0.05", "0.05~0.10", "0.10~0.15", "0.15~0.20", "0.20~0.30", "0.30~0.40", "0.40+"]
        counts = [0] * len(labels)
        n = 0
        for c in group:
            v = c.get("ultimateDelta")
            if v is None:
                continue
            n += 1
            for i in range(len(edges) - 1):
                if edges[i] <= v < edges[i + 1]:
                    counts[i] += 1
                    break
        return {"labels": labels, "counts": counts, "n": n}

    tag_combo_counts = Counter()
    for c in clips:
        tag_combo_counts[tuple(sorted(c.get("tags", [])))] += 1

    region_counts = Counter(c.get("region") for c in clips if c.get("region"))
    character_counts = Counter(c.get("myCharacter") for c in clips if c.get("myCharacter"))
    game_day_counts = Counter(c.get("gameDay") for c in clips if c.get("gameDay") is not None)
    day_night_counts = Counter(c.get("dayNight") for c in clips if c.get("dayNight"))
    game_mode_counts = Counter(c.get("gameMode") for c in clips if c.get("gameMode"))
    revive_cost_counts = Counter(c.get("reviveCost") for c in clips if c.get("reviveCost"))
    label_source_counts = Counter(c.get("labelSource") for c in clips)
    label_conflict = sum(1 for c in clips if c.get("labelConflict"))

    matches = defaultdict(lambda: {"total": 0, "pvp": 0, "pve": 0})
    for c in clips:
        m = matches[c["_match"]]
        m["total"] += 1
        if c.get("userLabel") == "pvp":
            m["pvp"] += 1
        elif c.get("userLabel") == "pve":
            m["pve"] += 1

    durations_pvp = [c["durationSec"] for c in pvp if c.get("durationSec") is not None]
    durations_pve = [c["durationSec"] for c in pve if c.get("durationSec") is not None]

    def duration_hist(group):
        edges = [0, 15, 30, 60, 90, 120, 180, 100000]
        labels = ["0-15s", "15-30s", "30-60s", "60-90s", "90-120s", "120-180s", "180s+"]
        counts = [0] * len(labels)
        for v in group:
            for i in range(len(edges) - 1):
                if edges[i] <= v < edges[i + 1]:
                    counts[i] += 1
                    break
        return {"labels": labels, "counts": counts}

    ultimate_used_by_label = {
        "pvp": sum(1 for c in pvp if "ultimate_used" in (c.get("pvpSignals") or [])),
        "pve": sum(1 for c in pve if "ultimate_used" in (c.get("pvpSignals") or [])),
    }

    evidence_signals = {"kill_delta", "assist_delta", "death", "teammate_death"}

    def has_confirmed_evidence(c):
        return bool(evidence_signals & set(c.get("pvpSignals") or []))

    confirmed_pvp = sum(1 for c in pvp if has_confirmed_evidence(c))
    confirmed_pve = sum(1 for c in pve if has_confirmed_evidence(c))
    no_evidence_pvp = [c for c in pvp if not (c.get("pvpSignals") or [])]
    no_evidence_pve = [c for c in pve if not (c.get("pvpSignals") or [])]

    out = {
        "total": total,
        "labeled": len(labeled),
        "pvpCount": len(pvp),
        "pveCount": len(pve),
        "unlabeledCount": len(unlabeled),
        "tagCounts": dict(tag_counts),
        "tagComboCounts": {" + ".join(k) if k else "(없음)": v for k, v in tag_combo_counts.most_common()},
        "signalCounts": dict(signal_counts),
        "scoreHistPvp": score_hist(pvp),
        "scoreHistPve": score_hist(pve),
        "ultimateDeltaHistPvp": ultimate_delta_hist(pvp),
        "ultimateDeltaHistPve": ultimate_delta_hist(pve),
        "ultimateUsedByLabel": ultimate_used_by_label,
        "regionCounts": dict(region_counts.most_common()),
        "characterCounts": dict(character_counts.most_common()),
        "gameDayCounts": {str(k): v for k, v in sorted(game_day_counts.items())},
        "dayNightCounts": dict(day_night_counts),
        "gameModeCounts": dict(game_mode_counts),
        "reviveCostCounts": dict(revive_cost_counts),
        "labelSourceCounts": {str(k): v for k, v in label_source_counts.items()},
        "labelConflictCount": label_conflict,
        "matches": {k: v for k, v in sorted(matches.items())},
        "matchCount": len(matches),
        "durationHistPvp": duration_hist(durations_pvp),
        "durationHistPve": duration_hist(durations_pve),
        "durationMeanPvp": round(sum(durations_pvp) / len(durations_pvp), 1) if durations_pvp else None,
        "durationMeanPve": round(sum(durations_pve) / len(durations_pve), 1) if durations_pve else None,
        "confirmedEvidencePvp": confirmed_pvp,
        "confirmedEvidencePve": confirmed_pve,
        "noEvidencePvpCount": len(no_evidence_pvp),
        "noEvidencePveCount": len(no_evidence_pve),
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
