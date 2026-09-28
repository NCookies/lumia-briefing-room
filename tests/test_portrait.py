import numpy as np

from lumia_briefing_room.detect.portrait import crop_portraits, find_portraits_in_frames
from lumia_briefing_room.profiles.models import ResolutionProfile

PROFILE = ResolutionProfile.for_resolution(2560, 1440)


def _blank_frame() -> np.ndarray:
    return np.full((1440, 2560, 3), 20, dtype=np.uint8)


def _paint(frame: np.ndarray, roi_name: str, color: tuple[int, int, int]) -> None:
    roi = PROFILE.rois[roi_name]
    frame[roi.y0 : roi.y1, roi.x0 : roi.x1] = color


def _team_intro_frame(*, me=(1, 2, 3), teammate1=(4, 5, 6), teammate2=(7, 8, 9)) -> np.ndarray:
    """미니맵 헤더는 보이고 체력바는 없는(팀 소개 화면) 프레임."""
    frame = _blank_frame()
    _paint(frame, "minimap_icons", (210, 210, 210))
    _paint(frame, "portrait", me)
    _paint(frame, "teammate1", teammate1)
    _paint(frame, "teammate2", teammate2)
    return frame


def _ingame_frame() -> np.ndarray:
    """미니맵도 체력바도 있는(실제 인게임) 프레임."""
    frame = _blank_frame()
    _paint(frame, "minimap_icons", (210, 210, 210))
    _paint(frame, "hp_strip", (90, 220, 40))
    return frame


def _loading_frame() -> np.ndarray:
    """미니맵조차 없는(로딩·로비) 프레임."""
    return _blank_frame()


def test_crop_portraits_slices_out_the_three_rois():
    frame = _team_intro_frame(me=(11, 12, 13), teammate1=(21, 22, 23), teammate2=(31, 32, 33))

    crops = crop_portraits(frame, PROFILE)

    assert tuple(crops.me[0, 0]) == (11, 12, 13)
    assert tuple(crops.teammate1[0, 0]) == (21, 22, 23)
    assert tuple(crops.teammate2[0, 0]) == (31, 32, 33)


def test_find_portraits_in_frames_stops_at_the_first_team_intro_frame():
    frames = [
        (0.0, _loading_frame()),
        (3.0, _loading_frame()),
        (6.0, _team_intro_frame(me=(9, 9, 9))),
        (9.0, _ingame_frame()),
    ]

    found = find_portraits_in_frames(frames, PROFILE)

    assert found is not None
    assert tuple(found.me[0, 0]) == (9, 9, 9)


def test_find_portraits_in_frames_gives_up_once_the_real_game_starts():
    frames = [(0.0, _loading_frame()), (3.0, _ingame_frame()), (6.0, _team_intro_frame())]

    assert find_portraits_in_frames(frames, PROFILE) is None


def test_find_portraits_in_frames_returns_none_when_nothing_matches():
    frames = [(0.0, _loading_frame()), (3.0, _loading_frame())]

    assert find_portraits_in_frames(frames, PROFILE) is None
