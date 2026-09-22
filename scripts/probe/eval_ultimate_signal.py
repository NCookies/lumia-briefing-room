"""일회성 조사 도구: 궁극기(R) 쿨타임 진입 신호를 라벨 전체에 대고 검증 (SPEC §2.12 #9).

각 라벨된 클립을 몇 초 간격으로 샘플링해 R 칸의 "파란기 비율"(ultimate_skill.py)을 재고,
클립 구간 안에서 그 값이 임계를 넘은 적이 있는지(=궁을 썼는지)를 교전/사냥 라벨과 대조한다.

★ 1차 결과 (전역 고정 임계) 는 가짜 신호였다 — 세션(캐릭터)마다 R 아이콘 원화 자체의
파란기 베이스라인이 달라서, 캐릭터가 바뀌면 궁을 안 써도 항상 ~0.25 근방이 나오는 경우가
있었다. 그래서 **클립 자체의 최솟값(그 클립에서 가장 "덜 파란" 순간 = 준비 상태로 추정)을
베이스라인으로 잡고, 최댓값과의 차이(delta)로 판정**하도록 바꿨다 — 진짜로 쓴 클립은
쿨타임 진입 시 값이 크게 뛰고, 안 쓴 클립은 캐릭터가 뭐든 값이 편평하게 유지될 것이라는
가설.

usage: eval_ultimate_signal.py <clips_dir> [--limit N] [--step SEC]
"""
import sys
import json
import glob
import os
import cv2

sys.path.insert(0, os.path.dirname(__file__))
from ultimate_skill import blue_tint_fraction  # noqa: E402

DELTA_THRESHOLD = 0.15


def sample_clip(path, duration, step):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return []
    fracs = []
    t = 0.0
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if ok:
            fracs.append(blue_tint_fraction(frame))
        t += step
    cap.release()
    return fracs


def main():
    clips_dir = sys.argv[1]
    limit = None
    step = 8.0
    args = sys.argv[2:]
    for i, a in enumerate(args):
        if a == "--limit":
            limit = int(args[i + 1])
        if a == "--step":
            step = float(args[i + 1])

    rows = []
    for jf in sorted(glob.glob(os.path.join(clips_dir, "*.json"))):
        d = json.load(open(jf, encoding="utf-8"))
        label = d.get("userLabel")
        if label not in ("pvp", "pve"):
            continue
        mp4 = jf[:-5] + ".mp4"
        if not os.path.exists(mp4):
            continue
        rows.append((mp4, label, d.get("durationSec") or 30.0, d.get("tags") or []))

    if limit:
        rows = rows[:limit]

    print(f"클립 {len(rows)}개 처리 (step={step}s)")
    results = []
    for i, (mp4, label, dur, tags) in enumerate(rows):
        fracs = sample_clip(mp4, dur, step)
        if not fracs:
            continue
        lo, hi = min(fracs), max(fracs)
        delta = hi - lo
        used = delta >= DELTA_THRESHOLD
        results.append((os.path.basename(mp4), label, lo, hi, delta, used, tags))
        print(f"[{i+1}/{len(rows)}] {os.path.basename(mp4):>28} {label:>3}  "
              f"min={lo:.3f} max={hi:.3f} delta={delta:.3f}  궁사용={used}  tags={tags}")

    pvp = [r for r in results if r[1] == "pvp"]
    pve = [r for r in results if r[1] == "pve"]
    pvp_used = sum(1 for r in pvp if r[5])
    pve_used = sum(1 for r in pve if r[5])
    print()
    print(f"pvp {len(pvp)}개 중 궁 사용 검출 {pvp_used}개 ({pvp_used/len(pvp)*100:.0f}%)" if pvp else "pvp 0개")
    print(f"pve {len(pve)}개 중 궁 사용 검출 {pve_used}개 ({pve_used/len(pve)*100:.0f}%)" if pve else "pve 0개")

    labels = [1 if r[1] == "pvp" else 0 for r in results]
    scores = [r[4] for r in results]  # delta
    n1 = sum(labels)
    n0 = len(labels) - n1
    if n1 and n0:
        ranked = sorted(range(len(scores)), key=lambda i: scores[i])
        ranks = [0] * len(scores)
        for rank, idx in enumerate(ranked, start=1):
            ranks[idx] = rank
        sum_ranks_pos = sum(ranks[i] for i in range(len(labels)) if labels[i] == 1)
        auc = (sum_ranks_pos - n1 * (n1 + 1) / 2) / (n1 * n0)
        print(f"AUC (delta) = {auc:.3f}  (n_pvp={n1}, n_pve={n0})")


if __name__ == "__main__":
    main()
