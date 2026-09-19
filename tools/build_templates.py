"""라벨셋(숫자별 크롭 PNG + labels.jsonl)에서 숫자 본보기(알파 템플릿)를 만든다.

usage:
    python tools/build_templates.py <frames_dir> <labels.jsonl> <output.npz>

labels.jsonl 한 줄: {"file": "0001.png", "digit": 3}
크롭은 전부 같은 해상도 프로필의 같은 ROI 크기여야 한다.

개발 도구다. scripts/probe/ 와 달리 실사용하며 계속 돌린다 (plan.md §2).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lumia_briefing_room.detect.counter import save_templates  # noqa: E402
from lumia_briefing_room.detect.glyph import build_template  # noqa: E402


def load_labeled_samples(
    frames_dir: Path, labels_path: Path
) -> dict[int, list[np.ndarray]]:
    samples: dict[int, list[np.ndarray]] = {}
    with open(labels_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            digit = int(entry["digit"])
            img = np.array(Image.open(frames_dir / entry["file"]).convert("RGB"))
            samples.setdefault(digit, []).append(img)
    return samples


def build_templates(samples: dict[int, list[np.ndarray]]) -> dict[int, np.ndarray]:
    templates: dict[int, np.ndarray] = {}
    for digit, imgs in samples.items():
        if not imgs:
            continue
        shapes = {img.shape for img in imgs}
        if len(shapes) != 1:
            raise ValueError(f"digit {digit}: 크롭 크기가 서로 다르다 {shapes}")
        templates[digit] = build_template(np.stack(imgs))
    return templates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames_dir", type=Path)
    parser.add_argument("labels", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    samples = load_labeled_samples(args.frames_dir, args.labels)
    templates = build_templates(samples)
    if not templates:
        raise SystemExit("라벨된 샘플이 없다")

    save_templates(templates, args.output)
    for digit in sorted(templates):
        print(f"digit {digit}: {len(samples[digit])} 샘플")


if __name__ == "__main__":
    main()
