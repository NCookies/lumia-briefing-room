"""수집한 헤더 crop 을 시각적으로 군집화한다. 군집 하나 = 지역명 하나. (plan-pvp 3단계)

대표 이미지를 사람이(또는 내가 눈으로) 읽어 이름을 붙인다.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lumia_briefing_room.detect.glyph import similarity  # noqa: E402
from lumia_briefing_room.detect.region import region_score  # noqa: E402

THRESH = 0.55


def main(hdr_dir, out_png):
    files = sorted(Path(hdr_dir).rglob("h_*.png"))
    clusters = []
    for f in files:
        rgb = np.asarray(Image.open(f).convert("RGB"))
        s = region_score(rgb, v_lo=170)
        if s.mean() < 0.005:
            continue
        for c in clusters:
            if similarity(s, c["rep"]) >= THRESH:
                c["n"] += 1
                c["members"].append(f)
                break
        else:
            clusters.append({"rep": s, "n": 1, "file": f, "members": [f]})
    clusters.sort(key=lambda c: -c["n"])
    print("군집", len(clusters), "/ 헤더", len(files))
    for i, c in enumerate(clusters):
        print(i, c["n"], c["file"].parent.name[-9:], c["file"].name)
    cols = 4
    w, h = 400, 68
    rows = (len(clusters) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h))
    for i, c in enumerate(clusters):
        im = Image.open(c["file"]).convert("RGB").resize((w, h), Image.LANCZOS)
        ImageDraw.Draw(im).text((4, 2), f"#{i} n={c['n']}", fill=(255, 255, 0))
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(out_png)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
