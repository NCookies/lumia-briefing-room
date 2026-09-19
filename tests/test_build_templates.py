import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from build_templates import build_templates, load_labeled_samples  # noqa: E402

from lumia_briefing_room.detect.counter import load_templates, save_templates


def test_load_labeled_samples_groups_by_digit(tmp_path, render_digit, compose):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    labels_path = tmp_path / "labels.jsonl"

    entries = []
    for i, digit in enumerate([3, 3, 7]):
        img = compose(render_digit(digit), (50, 60, 70))
        filename = f"{i:04d}.png"
        Image.fromarray(img).save(frames_dir / filename)
        entries.append({"file": filename, "digit": digit})

    with open(labels_path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    samples = load_labeled_samples(frames_dir, labels_path)

    assert len(samples[3]) == 2
    assert len(samples[7]) == 1
    assert samples[3][0].shape == samples[7][0].shape


def test_load_labeled_samples_skips_blank_lines(tmp_path, render_digit, compose):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    labels_path = tmp_path / "labels.jsonl"
    img = compose(render_digit(1), (10, 10, 10))
    Image.fromarray(img).save(frames_dir / "a.png")
    labels_path.write_text(
        '\n{"file": "a.png", "digit": 1}\n\n', encoding="utf-8"
    )

    samples = load_labeled_samples(frames_dir, labels_path)
    assert len(samples[1]) == 1


def test_build_templates_produces_template_per_digit(render_digit, compose):
    rng = np.random.default_rng(1)
    samples = {}
    for digit in (0, 1):
        alpha = render_digit(digit)
        samples[digit] = [
            compose(alpha, tuple(int(x) for x in rng.integers(0, 150, size=3)))
            for _ in range(10)
        ]

    templates = build_templates(samples)

    assert set(templates) == {0, 1}
    for t in templates.values():
        assert t.dtype == np.float32
        assert t.shape == (17, 12)


def test_build_templates_rejects_mismatched_shapes():
    samples = {5: [np.zeros((10, 10, 3), dtype=np.uint8), np.zeros((12, 10, 3), dtype=np.uint8)]}
    with pytest.raises(ValueError):
        build_templates(samples)


def test_build_templates_skips_empty_digit_lists():
    samples = {3: [], 4: [np.zeros((5, 5, 3), dtype=np.uint8)] * 3}
    templates = build_templates(samples)
    assert set(templates) == {4}


def test_save_and_load_templates_roundtrip(tmp_path):
    templates = {
        0: np.random.rand(17, 12).astype(np.float32),
        1: np.random.rand(17, 12).astype(np.float32),
    }
    path = tmp_path / "digits.npz"

    save_templates(templates, path)
    loaded = load_templates(path)

    assert set(loaded) == {0, 1}
    assert np.array_equal(loaded[0], templates[0])
    assert np.array_equal(loaded[1], templates[1])
