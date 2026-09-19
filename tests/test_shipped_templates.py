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
