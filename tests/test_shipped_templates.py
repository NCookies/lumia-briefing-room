from lumia_briefing_room.detect.counter import load_templates
from lumia_briefing_room.profiles.models import ResolutionProfile


def test_2560x1440_profile_has_shipped_real_templates():
    profile = ResolutionProfile.builtin(2560, 1440)
    assert profile.templates is not None
    assert profile.templates.exists()


def test_shipped_templates_load_and_cover_common_digits():
    profile = ResolutionProfile.builtin(2560, 1440)
    templates = load_templates(profile.templates)
    # 실제 녹화본에서 뽑은 라벨셋 기준 (data/templates/digits/2560x1440_labels.jsonl)
    for digit in (0, 1, 2):
        assert digit in templates
        h, w = templates[digit].shape
        assert (h, w) == (profile.rois["k_value"].height, profile.rois["k_value"].width)


def test_shipped_templates_read_their_own_labeled_samples_including_7_and_8():
    import json
    from pathlib import Path

    import numpy as np
    from PIL import Image

    from lumia_briefing_room.detect.counter import read_field
    from lumia_briefing_room.detect.glyph import text_score

    profile = ResolutionProfile.builtin(2560, 1440)
    templates = load_templates(profile.templates)
    root = Path(profile.templates).parent
    labels = [json.loads(l) for l in (root / "2560x1440_labels.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    assert {7, 8} <= set(templates)
    wrong = []
    for entry in labels:
        img = np.array(Image.open(root / "2560x1440_samples" / entry["file"]).convert("RGB"))
        value = read_field(text_score(img), templates).value
        if value is not None and value != entry["digit"]:
            wrong.append((entry["file"], entry["digit"], value))
    assert wrong == []
