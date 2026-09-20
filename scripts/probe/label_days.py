"""일차 텍스트 crop 을 군집화해 라벨셋(샘플 PNG + labels.jsonl)을 만든다. (plan-pvp 3단계)

label_regions.py 와 같은 방식: 임계 0.8 로 군집을 순수하게 만들고 대표를 눈으로 읽어 숫자를 붙인다.
사용법: label_days.py <crops_dir> <out_dir> [--sheet sheet.png]  (NAMES 가 비어 있으면 대표 시트만 만든다)
"""
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lumia_briefing_room.detect.glyph import similarity  # noqa: E402
from lumia_briefing_room.detect.day import white_score as region_score  # noqa: E402

THRESH = 0.96
DIGIT = (9, 24)  # 60px 크롭에서 숫자 한 글자만 (공통 글자 `일` 은 뺀다)
MAX_PER_NAME = 10
NAMES: dict[int, str | None] = {
    0: "1", 1: "2", 2: "4", 3: "3", 4: "5", 5: "6", 6: "7", 7: None, 8: "8", 9: "4", 10: "3",
    11: "5", 12: "3", 13: "3", 14: "5", 15: "5", 16: "5", 17: "6", 18: "6", 19: "6", 20: None,
}


def cluster(crops_dir) -> list[list[Path]]:
    clusters = []
    for f in sorted(Path(crops_dir).rglob("c_*.png")):
        s = region_score(np.asarray(Image.open(f).convert("RGB"))[:, DIGIT[0]:DIGIT[1]])
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


def sheet(clusters, out_png):
    w, h, k = 120, 52, 4
    img = Image.new("RGB", (2 * (70 + k * w), ((len(clusters) + 1) // 2) * h), (15, 15, 15))
    d = ImageDraw.Draw(img)
    for i, m in enumerate(clusters):
        x0, y0 = (i % 2) * (70 + k * w), (i // 2) * h
        d.text((x0 + 3, y0 + 18), f"#{i} n={len(m)}", fill=(255, 255, 0))
        for j, f in enumerate(m[:: max(len(m) // k, 1)][:k]):
            img.paste(Image.open(f).convert("RGB").crop((DIGIT[0], 0, DIGIT[1], 26)).resize((w, h - 2)), (x0 + 70 + j * w, y0))
    img.save(out_png)


def main(crops_dir, out_dir, sheet_png=None):
    clusters = cluster(crops_dir)
    print("군집", len(clusters), [len(m) for m in clusters])
    if sheet_png:
        sheet(clusters, sheet_png)
    if not NAMES:
        return
    grouped = defaultdict(list)
    for i, m in enumerate(clusters):
        if NAMES.get(i):
            grouped[NAMES[i]].extend(m)
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    rows = []
    for name, members in grouped.items():
        for k, f in enumerate(members[:: max(len(members) // MAX_PER_NAME, 1)][:MAX_PER_NAME]):
            fname = f"{name}_{k:02d}.png"
            Image.open(f).convert("RGB").crop((DIGIT[0], 0, DIGIT[1], 26)).save(out / fname)
            rows.append({"file": fname, "name": name})
    with open(out.parent / "2560x1440_labels.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("이름", sorted(grouped), "샘플", len(rows))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[4] if len(sys.argv) > 4 else None)
