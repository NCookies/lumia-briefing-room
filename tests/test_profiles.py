from lumia_briefing_room.profiles.models import Roi, ResolutionProfile


def test_roi_scaled_scales_all_edges():
    roi = Roi(x0=100, y0=200, x1=150, y1=250)
    scaled = roi.scaled(2.0, 1.5)
    assert scaled == Roi(x0=200, y0=300, x1=300, y1=375)


def test_roi_scaled_rounds_to_int():
    roi = Roi(x0=1, y0=1, x1=4, y1=4)
    scaled = roi.scaled(1.5, 1.5)
    assert scaled == Roi(x0=2, y0=2, x1=6, y1=6)


def test_roi_width_height():
    roi = Roi(x0=10, y0=20, x1=40, y1=60)
    assert roi.width == 30
    assert roi.height == 40


def test_builtin_2560x1440_profile_has_expected_rois():
    profile = ResolutionProfile.builtin(2560, 1440)
    assert profile.measured is True
    assert profile.width == 2560
    assert profile.height == 1440
    for name in ("badge", "face", "k_value", "a_value", "day_night", "day_text",
                 "teammate1", "teammate2"):
        assert name in profile.rois


def test_unknown_resolution_falls_back_to_proportional_scaling():
    profile = ResolutionProfile.for_resolution(1600, 900)
    assert profile.measured is False
    base = ResolutionProfile.builtin(2560, 1440)
    expected = base.rois["k_value"].scaled(1600 / 2560, 900 / 1440)
    assert profile.rois["k_value"] == expected


def test_known_resolution_returns_measured_profile():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    assert profile.measured is True


def test_profile_without_templates_has_none_path():
    profile = ResolutionProfile.for_resolution(1600, 900)
    assert profile.templates is None


def test_counter_rois_are_as_wide_as_the_digit_templates():
    from lumia_briefing_room.detect.counter import load_templates

    profile = ResolutionProfile.for_resolution(2560, 1440)
    template_width = next(iter(load_templates(profile.templates).values())).shape[1]

    assert profile.rois["k_value"].width == template_width
    assert profile.rois["a_value"].width == template_width


def test_measured_profile_points_at_region_templates():
    profile = ResolutionProfile.for_resolution(2560, 1440)

    assert profile.region_templates is not None
    assert profile.region_templates.exists()


def test_unmeasured_profile_has_no_region_templates():
    assert ResolutionProfile.for_resolution(1600, 900).region_templates is None


def test_measured_profile_points_at_day_templates_only_when_the_file_exists():
    profile = ResolutionProfile.for_resolution(2560, 1440)

    assert profile.day_templates is None or profile.day_templates.exists()
    assert ResolutionProfile.for_resolution(1600, 900).day_templates is None


def test_builtin_1920x1080_profile_is_measured_and_normalized_to_1440p():
    profile = ResolutionProfile.for_resolution(1920, 1080)
    base = ResolutionProfile.builtin(2560, 1440)

    assert profile.measured is True
    assert (profile.width, profile.height) == (1920, 1080)
    assert profile.rois["k_value"] == base.rois["k_value"].scaled(0.75, 0.75)
    assert profile.reference_rois == base.rois


def test_normalized_profile_reuses_the_reference_templates():
    profile = ResolutionProfile.for_resolution(1920, 1080)
    base = ResolutionProfile.builtin(2560, 1440)

    assert profile.templates == base.templates
    assert profile.region_templates == base.region_templates
    assert profile.day_templates == base.day_templates


def test_crop_upsizes_normalized_profile_pieces_to_reference_size():
    import numpy as np

    profile = ResolutionProfile.for_resolution(1920, 1080)
    base = ResolutionProfile.builtin(2560, 1440)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    for name in ("k_value", "badge", "minimap", "day_digit"):
        piece = profile.crop(frame, name)
        assert piece.shape[:2] == (base.rois[name].height, base.rois[name].width)


def test_crop_of_reference_profile_is_the_plain_crop():
    import numpy as np

    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = np.arange(1440 * 2560 * 3, dtype=np.uint32).astype(np.uint8).reshape(1440, 2560, 3)

    roi = profile.rois["k_value"]
    assert np.array_equal(
        profile.crop(frame, "k_value"), frame[roi.y0 : roi.y1, roi.x0 : roi.x1]
    )
