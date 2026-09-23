from lumia_briefing_room.profiles.models import measured_resolutions
from lumia_briefing_room.resolution_support import classify_resolution


def test_measured_resolutions_come_from_builtin_profiles():
    assert (2560, 1440) in measured_resolutions()
    assert (1920, 1080) in measured_resolutions()


def test_measured_profiles_are_supported():
    for size in [(2560, 1440), (1920, 1080)]:
        assert classify_resolution(*size).kind == "measured"


def test_other_16_9_sizes_are_scaled():
    for size in [(3840, 2160), (1600, 900), (1280, 720)]:
        assert classify_resolution(*size).kind == "scaled"


def test_non_16_9_ratios_are_unverified():
    for size in [(1920, 1200), (2560, 1600), (3440, 1440), (1280, 1024)]:
        result = classify_resolution(*size)
        assert result.kind == "unsupported_ratio", size
        assert "보장" in result.message


def test_result_reports_size_and_message():
    result = classify_resolution(2560, 1440)
    assert (result.width, result.height) == (2560, 1440)
    assert "2560x1440" in result.message
