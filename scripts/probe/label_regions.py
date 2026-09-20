"""헤더 crop 을 군집화해 지역명 라벨셋(샘플 PNG + labels.jsonl)을 만든다. (plan-pvp 3단계)

군집 임계 0.55 로는 모양이 비슷한 낱말(소방서/경찰서, 학교/항구, 성당/공장, 연못/병원)이
한 군집에 섞였다. 0.8 로 올려 군집이 순수해진 것을 대표 5장씩 눈으로 확인한 뒤 이름을 붙였다.
같은 이름이 군집 여러 개로 갈린다(글자색 흰/빨강/주황, 배경 차이) — 그대로 이름별로 합친다.
"""
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lumia_briefing_room.detect.glyph import similarity  # noqa: E402
from lumia_briefing_room.detect.region import region_score  # noqa: E402

THRESH = 0.8
TEXT_WIDTH = 120
MAX_PER_NAME = 10
NAMES = {
    0: "소방서", 1: "묘지", 2: "연못", 3: "경찰서", 4: "학교", 5: "절", 6: "병원", 7: "주유소",
    8: "바지선", 9: "개울", 10: "골목길", 11: "공장", 12: "항구", 13: "공장", 14: "전투 연구실",
    15: "브리핑 룸", 16: "양궁장", 17: "성당", 18: "항구", 19: "호텔", 20: "연구소",
    21: "브리핑 룸", 22: "숲", 23: "공장", 24: "절", 25: "연못", 26: "묘지", 27: "공장",
    28: "양궁장", 29: "학교", 30: "개울", 31: "소방서", 32: "묘지", 33: "창고", 34: "묘지",
    35: None,
}


def crop_text(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))[:, :TEXT_WIDTH]


def cluster(hdr_dir) -> list[list[Path]]:
    clusters = []
    for f in sorted(Path(hdr_dir).rglob("h_*.png")):
        s = region_score(crop_text(f), v_lo=170)
        if s.mean() < 0.005:
            continue
        for c in clusters:
            if similarity(s, c["rep"]) >= THRESH:
                c["members"].append(f)
                break
        else:
            clusters.append({"rep": s, "members": [f]})
    clusters.sort(key=lambda c: -len(c["members"]))
    return [c["members"] for c in clusters]


def by_name(hdr_dir) -> dict[str, list[Path]]:
    grouped = defaultdict(list)
    for i, members in enumerate(cluster(hdr_dir)):
        if NAMES.get(i):
            grouped[NAMES[i]].extend(members)
    return grouped


def main(hdr_dir, out_dir):
    grouped = by_name(hdr_dir)
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    rows = []
    for name, members in grouped.items():
        step = max(len(members) // MAX_PER_NAME, 1)
        for k, f in enumerate(members[::step][:MAX_PER_NAME]):
            fname = f"{name.replace(' ', '_')}_{k:02d}.png"
            Image.fromarray(crop_text(f)).save(out / fname)
            rows.append({"file": fname, "name": name})
    with open(out.parent / "2560x1440_labels.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("이름", len(grouped), "샘플", len(rows))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
