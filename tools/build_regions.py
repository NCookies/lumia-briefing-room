"""라벨셋(지역명 헤더 크롭 PNG + labels.jsonl)에서 지역명 본보기를 만든다.

usage:
    python tools/build_regions.py <frames_dir> <labels.jsonl> <output.npz>

labels.jsonl 한 줄: {"file": "묘지_00.png", "name": "묘지"}
크롭은 전부 같은 해상도 프로필의 같은 ROI 크기여야 한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lumia_briefing_room.detect.region import (  # noqa: E402
    build_region_template,
    region_score,
    save_region_templates,
)


def load_labeled_region_samples(frames_dir: Path, labels_path: Path) -> dict[str, list[np.ndarray]]:
    samples: dict[str, list[np.ndarray]] = {}
    with open(labels_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            img = np.array(Image.open(frames_dir / entry["file"]).convert("RGB"))
            samples.setdefault(entry["name"], []).append(img)
    return samples


def build_region_templates(samples: dict[str, list[np.ndarray]]) -> dict[str, np.ndarray]:
    templates: dict[str, np.ndarray] = {}
    for name, imgs in samples.items():
        shapes = {img.shape for img in imgs}
        if len(shapes) != 1:
            raise ValueError(f"{name}: 크롭 크기가 서로 다르다 {shapes}")
        templates[name] = build_region_template([region_score(img) for img in imgs])
    return templates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames_dir", type=Path)
    parser.add_argument("labels", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    samples = load_labeled_region_samples(args.frames_dir, args.labels)
    templates = build_region_templates(samples)
    if not templates:
        raise SystemExit("라벨된 샘플이 없다")

    save_region_templates(templates, args.output)
    for name in sorted(templates):
        print(f"{name}: {len(samples[name])} 샘플")


if __name__ == "__main__":
    main()
