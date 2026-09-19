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
    profile = ResolutionProfile.for_resolution(1920, 1080)
    assert profile.measured is False
    base = ResolutionProfile.builtin(2560, 1440)
    expected = base.rois["k_value"].scaled(1920 / 2560, 1080 / 1440)
    assert profile.rois["k_value"] == expected


def test_known_resolution_returns_measured_profile():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    assert profile.measured is True


def test_profile_without_templates_has_none_path():
    profile = ResolutionProfile.for_resolution(1920, 1080)
    assert profile.templates is None
