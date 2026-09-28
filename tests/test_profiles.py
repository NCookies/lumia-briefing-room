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
    # 코발트 전용 ROI(phase_digit 등)는 해상도마다 따로 실측하므로 reference_rois 로
    # 안 빌려준다 - 안 그러면 1920x1080 이 자신의 네이티브 코발트 크롭을 2560x1440 의
    # 값으로 엉뚱하게 확대한다(2026-09-28 실사용 작업 중 발견).
    from lumia_briefing_room.profiles.models import _RESOLUTION_NATIVE_ONLY_ROIS

    assert profile.reference_rois == {
        k: v for k, v in base.rois.items() if k not in _RESOLUTION_NATIVE_ONLY_ROIS
    }
    assert set(_RESOLUTION_NATIVE_ONLY_ROIS) & set(profile.reference_rois) == set()


def test_normalized_profile_reuses_the_reference_templates():
    profile = ResolutionProfile.for_resolution(1920, 1080)
    base = ResolutionProfile.builtin(2560, 1440)

    assert profile.templates == base.templates
    assert profile.region_templates == base.region_templates
    assert profile.day_templates == base.day_templates


def test_phase_templates_are_looked_up_at_the_profile_own_resolution():
    """plan.md §10-1: 코발트는 기준 해상도(2560x1440) 녹화가 없어 정규화하지 않는다."""
    profile = ResolutionProfile.for_resolution(1920, 1080)

    assert profile.phase_templates is None or "1920x1080" in str(profile.phase_templates)


def test_base_resolution_now_has_real_measured_phase_data():
    """예전엔 "코발트는 기준 해상도(2560x1440) 녹화가 없어 정규화하지 않는다"는 전제로
    이 프로필에 phase_digit 이 없다고 단정했다. 2026-09-28 실사용 보고(스팀 녹화로 직접
    플레이한 코발트 게임이 거의 인식 안 됨)로 이 해상도의 실제 게임 녹화를 확보해 실측
    본보기를 만들었다 - 이제는 있어야 한다."""
    base = ResolutionProfile.builtin(2560, 1440)

    assert "phase_digit" in base.rois
    assert base.phase_templates is not None and base.phase_templates.exists()


def test_resolution_native_cobalt_rois_never_leak_into_another_profiles_reference_size():
    """실사용 작업 중 발견한 회귀(2026-09-28): 1920x1080·2560x1440 모두 코발트 ROI를
    독립적으로 실측해 둔다(스트리머 VOD와 사용자 자신의 스팀 녹화가 화면 배치가 서로
    다르다, plan.md §10-8). `normalizedTo`(1920x1080 → 2560x1440)가 이름이 같다는
    이유만으로 2560x1440 쪽 좌표를 "기준 크기"로 빌려주면, `crop()`이 1920x1080 의
    멀쩡한 네이티브 코발트 크롭을 엉뚱한 크기로 확대해 버린다. `phase_digit` 크롭이
    두 해상도에서 서로 다른 실측 크기를 갖고 있어(우연히 같았으면 이 테스트는 못 잡는다)
    이 리크를 직접 재현해 잡는다."""
    import numpy as np

    profile_1080p = ResolutionProfile.for_resolution(1920, 1080)
    base_1440p = ResolutionProfile.builtin(2560, 1440)
    roi_1080p = profile_1080p.rois["phase_digit"]
    roi_1440p = base_1440p.rois["phase_digit"]
    assert (roi_1080p.width, roi_1080p.height) != (roi_1440p.width, roi_1440p.height)

    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    piece = profile_1080p.crop(frame, "phase_digit")

    assert piece.shape[:2] == (roi_1080p.height, roi_1080p.width)


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


def test_missing_templates_are_reported_not_silent(tmp_path, monkeypatch, caplog):
    import logging

    from lumia_briefing_room import paths
    from lumia_briefing_room.profiles.models import ResolutionProfile

    monkeypatch.setenv("LUMIA_RESOURCE_DIR", str(tmp_path))
    paths._warned.clear()
    with caplog.at_level(logging.WARNING, logger="lumia_briefing_room.paths"):
        profile = ResolutionProfile.builtin(2560, 1440)

    assert profile.templates is None and profile.region_templates is None and profile.day_templates is None
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "K/A 숫자 본보기" in messages and "지역명 본보기" in messages and "일차 본보기" in messages
