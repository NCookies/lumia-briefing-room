import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from build_regions import build_region_templates, load_labeled_region_samples  # noqa: E402

from lumia_briefing_room.detect.region import read_region, region_score


def _crop(seed: int, tint=(255, 255, 255)) -> np.ndarray:
    rng = np.random.default_rng(seed)
    mask = np.zeros((34, 110), bool)
    mask[8:26, 10:50] = rng.random((18, 40)) > 0.5
    img = np.full((34, 110, 3), 25, np.uint8)
    img[mask] = tint
    return img


def _write(tmp_path, entries):
    frames = tmp_path / "frames"
    frames.mkdir()
    with open(tmp_path / "labels.jsonl", "w", encoding="utf-8") as f:
        for i, (name, img) in enumerate(entries):
            filename = f"{i:03d}.png"
            Image.fromarray(img).save(frames / filename)
            f.write(json.dumps({"file": filename, "name": name}, ensure_ascii=False) + "\n")
    return frames, tmp_path / "labels.jsonl"


def test_load_labeled_region_samples_groups_by_name(tmp_path):
    frames, labels = _write(
        tmp_path,
        [("묘지", _crop(1)), ("묘지", _crop(1, (255, 160, 30))), ("학교", _crop(2))],
    )

    samples = load_labeled_region_samples(frames, labels)

    assert {k: len(v) for k, v in samples.items()} == {"묘지": 2, "학교": 1}


def test_build_region_templates_reads_back_every_name_regardless_of_text_color(tmp_path):
    frames, labels = _write(
        tmp_path,
        [
            ("묘지", _crop(1)), ("묘지", _crop(1, (255, 40, 40))),
            ("학교", _crop(2)), ("학교", _crop(2, (255, 160, 30))),
        ],
    )

    templates = build_region_templates(load_labeled_region_samples(frames, labels))

    for name, seed in (("묘지", 1), ("학교", 2)):
        for tint in ((255, 255, 255), (255, 40, 40), (255, 160, 30)):
            assert read_region(region_score(_crop(seed, tint)), templates).name == name


def test_white_score_option_builds_templates_that_ignore_background_color(tmp_path):
    from build_regions import build_region_templates
    from lumia_briefing_room.detect.day import white_score

    rng = np.random.default_rng(5)
    mask = rng.random((26, 15)) > 0.5

    def crop(bg):
        img = np.full((26, 15, 3), bg, np.uint8)
        img[mask] = (245, 240, 220)
        return img

    samples = {"6": [crop((20, 25, 35)), crop((175, 15, 15)), crop((190, 110, 30))]}

    template = build_region_templates(samples, score=white_score)["6"]

    for bg in ((20, 25, 35), (175, 15, 15), (190, 110, 30)):
        assert float(np.abs(white_score(crop(bg))[:, : template.shape[1]] - template).mean()) < 0.35
