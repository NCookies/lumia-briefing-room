import numpy as np

from lumia_briefing_room.detect.portrait import (
    crop_portraits,
    crops_look_like_portraits,
    find_portraits_in_frames,
)
from lumia_briefing_room.profiles.models import ResolutionProfile

PROFILE = ResolutionProfile.for_resolution(2560, 1440)
VIVID = (250, 60, 40)  # 밝고 채도 높은 색 - 초상화 그림 흉내


def _blank_frame() -> np.ndarray:
    return np.full((1440, 2560, 3), 20, dtype=np.uint8)


def _paint(frame: np.ndarray, roi_name: str, color: tuple[int, int, int]) -> None:
    roi = PROFILE.rois[roi_name]
    frame[roi.y0 : roi.y1, roi.x0 : roi.x1] = color


def _route_select_frame(*, me=VIVID, teammate1=VIVID, teammate2=VIVID) -> np.ndarray:
    """미니맵도 체력바도 없는(루트 선택 단계) 프레임에 초상화 3칸을 채운다."""
    frame = _blank_frame()
    _paint(frame, "portrait", me)
    _paint(frame, "teammate1", teammate1)
    _paint(frame, "teammate2", teammate2)
    return frame


def _lobby_frame() -> np.ndarray:
    """미니맵은 보이고 체력바는 없는(팀 로비, `spectating=True`) 프레임 - 이제는 포기 대상이다."""
    frame = _blank_frame()
    _paint(frame, "minimap_icons", (210, 210, 210))
    return frame


def _ingame_frame() -> np.ndarray:
    """미니맵도 체력바도 있는(실제 인게임, `spectating=False`) 프레임."""
    frame = _blank_frame()
    _paint(frame, "minimap_icons", (210, 210, 210))
    _paint(frame, "hp_strip", (90, 220, 40))
    return frame


def test_crop_portraits_slices_out_the_three_rois():
    frame = _route_select_frame(me=(11, 12, 13), teammate1=(21, 22, 23), teammate2=(31, 32, 33))

    crops = crop_portraits(frame, PROFILE)

    assert tuple(crops.me[0, 0]) == (11, 12, 13)
    assert tuple(crops.teammate1[0, 0]) == (21, 22, 23)
    assert tuple(crops.teammate2[0, 0]) == (31, 32, 33)


def test_crops_look_like_portraits_requires_all_three_vivid():
    vivid = crop_portraits(_route_select_frame(), PROFILE)
    assert crops_look_like_portraits(vivid) is True

    only_me = crop_portraits(_route_select_frame(teammate1=(20, 20, 20), teammate2=(20, 20, 20)), PROFILE)
    assert crops_look_like_portraits(only_me) is False


def test_find_portraits_in_frames_stops_at_the_first_frame_with_all_three_filled():
    winning_me_color = (250, 30, 200)
    frames = [
        (0.0, _blank_frame()),
        (3.0, _route_select_frame(teammate1=(20, 20, 20))),  # 아직 한 칸이 안 채워졌다
        (6.0, _route_select_frame(me=winning_me_color)),  # 이제 세 칸 다 채워졌다
    ]

    found = find_portraits_in_frames(frames, PROFILE)

    assert found is not None
    assert tuple(found.me[0, 0]) == winning_me_color


def test_find_portraits_in_frames_gives_up_once_the_team_lobby_appears():
    frames = [(0.0, _blank_frame()), (3.0, _lobby_frame()), (6.0, _route_select_frame())]

    assert find_portraits_in_frames(frames, PROFILE) is None


def test_find_portraits_in_frames_gives_up_once_real_gameplay_starts():
    """실측(2026-09-29): 빠르게 캐릭터·루트를 확정하는 경기는 몇 초 만에 로비를 지나쳐
    인게임까지 가 버릴 수 있다 - 그런 경기는 초상화를 못 얻고 포기한다(예외는 아님)."""
    frames = [(0.0, _blank_frame()), (3.0, _ingame_frame()), (6.0, _route_select_frame())]

    assert find_portraits_in_frames(frames, PROFILE) is None


def test_find_portraits_in_frames_returns_none_when_nothing_matches():
    frames = [(0.0, _blank_frame()), (3.0, _blank_frame())]

    assert find_portraits_in_frames(frames, PROFILE) is None
