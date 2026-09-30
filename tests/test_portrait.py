import dataclasses

import numpy as np

from lumia_briefing_room.detect.portrait import (
    crop_portraits,
    crops_look_like_portraits,
    find_portraits_in_frames,
)
from lumia_briefing_room.detect.types import PortraitCrops
from lumia_briefing_room.profiles.models import ResolutionProfile

PROFILE = ResolutionProfile.for_resolution(2560, 1440)
LEGACY_PROFILE = dataclasses.replace(
    PROFILE, rois={k: v for k, v in PROFILE.rois.items() if not k.startswith("select_")}
)
VIVID = (250, 60, 40)  # 밝고 채도 높은 색 - 초상화 그림 흉내
DIM = (20, 20, 20)


def _blank_frame() -> np.ndarray:
    return np.full((1440, 2560, 3), 20, dtype=np.uint8)


def _paint(frame: np.ndarray, roi_name: str, color: tuple[int, int, int]) -> None:
    roi = PROFILE.rois[roi_name]
    frame[roi.y0 : roi.y1, roi.x0 : roi.x1] = color


def _route_select_frame(*, me=VIVID, teammate1=VIVID, teammate2=VIVID) -> np.ndarray:
    """미니맵도 체력바도 없는(루트 선택 단계) 프레임 - 판정용 좁은 칸과 저장용 넓은 칸을 함께 채운다.

    실제 화면에서는 같은 그림이 두 칸(판정용 `portrait`, 저장용 `portrait_display`)에
    걸쳐 보이므로, 합성 테스트에서도 겹치는 두 ROI 모두에 같은 색을 칠해 흉내 낸다.
    """
    frame = _blank_frame()
    for base, color in [("portrait", me), ("teammate1", teammate1), ("teammate2", teammate2)]:
        _paint(frame, base, color)
        _paint(frame, f"{base}_display", color)
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


def test_crop_portraits_reads_the_wider_display_rois_not_the_narrow_detect_ones():
    """실사용 피드백(2026-09-29): 판정용 좁은 칸만 잘라 저장하면 얼굴만 남아 못생겨 보인다.
    저장은 상반신까지 나오는 `*_display` ROI 를 써야 한다."""
    frame = _blank_frame()
    _paint(frame, "portrait", (1, 1, 1))  # 판정용 칸 - 저장 결과에 섞이면 안 된다
    _paint(frame, "portrait_display", (11, 12, 13))
    _paint(frame, "teammate1_display", (21, 22, 23))
    _paint(frame, "teammate2_display", (31, 32, 33))

    crops = crop_portraits(frame, PROFILE)

    assert tuple(crops.me[0, 0]) == (11, 12, 13)
    assert tuple(crops.teammate1[0, 0]) == (21, 22, 23)
    assert tuple(crops.teammate2[0, 0]) == (31, 32, 33)


def test_crops_look_like_portraits_requires_all_three_vivid():
    def crops(me, teammate1, teammate2):
        block = lambda color: np.full((40, 40, 3), color, dtype=np.uint8)
        return PortraitCrops(me=block(me), teammate1=block(teammate1), teammate2=block(teammate2))

    assert crops_look_like_portraits(crops(VIVID, VIVID, VIVID)) is True
    assert crops_look_like_portraits(crops(VIVID, DIM, DIM)) is False
    assert crops_look_like_portraits(crops(DIM, DIM, DIM)) is False


def test_find_portraits_in_frames_stops_at_the_first_frame_with_all_three_filled():
    winning_me_color = (250, 30, 200)
    frames = [
        (0.0, _blank_frame()),
        (3.0, _route_select_frame(teammate1=DIM)),  # 아직 한 칸이 안 채워졌다
        (6.0, _route_select_frame(me=winning_me_color)),  # 이제 세 칸 다 채워졌다
    ]

    found = find_portraits_in_frames(frames, LEGACY_PROFILE)

    assert found is not None
    assert tuple(found.me[0, 0]) == winning_me_color


def test_find_portraits_in_frames_gives_up_once_the_team_lobby_settles_in():
    """2연속 이상 `spectating` 이 `None` 이 아니어야 진짜로 로비에 들어선 것으로 본다."""
    frames = [
        (0.0, _blank_frame()),
        (3.0, _lobby_frame()),
        (6.0, _lobby_frame()),
        (9.0, _route_select_frame()),
    ]

    assert find_portraits_in_frames(frames, LEGACY_PROFILE) is None


def test_find_portraits_in_frames_gives_up_once_real_gameplay_settles_in():
    """실측(2026-09-29): 빠르게 캐릭터·루트를 확정하는 경기는 몇 초 만에 로비를 지나쳐
    인게임까지 가 버릴 수 있다 - 그런 경기는 초상화를 못 얻고 포기한다(예외는 아님)."""
    frames = [
        (0.0, _blank_frame()),
        (3.0, _ingame_frame()),
        (6.0, _ingame_frame()),
        (9.0, _route_select_frame()),
    ]

    assert find_portraits_in_frames(frames, LEGACY_PROFILE) is None


def test_find_portraits_in_frames_tolerates_a_single_stray_non_none_reading():
    """재실측(2026-09-29): `matchStartUtc` 앞쪽을 훑을 때 맨 앞이 이전 경기의 로비 꼬리일 수 있고,
    관전 판정 자체가 가끔 낱개로 틀리기도 한다(팀 로비 원형 화면에서 실측 확인) - 한 프레임만
    `None` 이 아니면 포기하지 않고 계속 찾는다."""
    frames = [(0.0, _lobby_frame()), (3.0, _route_select_frame())]

    found = find_portraits_in_frames(frames, LEGACY_PROFILE)

    assert found is not None


def test_find_portraits_in_frames_returns_none_when_nothing_matches():
    frames = [(0.0, _blank_frame()), (3.0, _blank_frame())]

    assert find_portraits_in_frames(frames, LEGACY_PROFILE) is None


def _with_select_header(frame: np.ndarray) -> np.ndarray:
    """캐릭터·루트 선택 화면 머리띠 흉내: 시안색 남은 시간 + 어두운 바탕에 회색 제목 글자(`read_select_screen`)."""
    _paint(frame, "select_timer", (50, 180, 220))
    title = PROFILE.rois["select_title"]
    frame[title.y0 : title.y1, title.x0 : title.x1] = (35, 35, 35)
    stripe = max(1, round((title.y1 - title.y0) * 0.15))
    frame[title.y0 : title.y0 + stripe, title.x0 : title.x1] = (180, 180, 180)
    return frame


def _select_route_frame(**kwargs) -> np.ndarray:
    return _with_select_header(_route_select_frame(**kwargs))


def test_select_mode_finds_portraits_on_the_route_select_screen():
    frames = [(0.0, _blank_frame()), (3.0, _select_route_frame())]

    assert find_portraits_in_frames(frames, PROFILE) is not None


def test_select_mode_ignores_vivid_crops_outside_the_select_screen():
    """선택 화면 머리띠가 없으면(인게임 HUD·이전 경기 화면) 세 칸이 초상화처럼 보여도 받지 않는다."""
    frames = [(0.0, _route_select_frame()), (3.0, _blank_frame())]

    assert find_portraits_in_frames(frames, PROFILE) is None


def test_select_mode_is_not_stopped_by_frames_read_as_spectating():
    """실측(2026-09-30, 치지직 1080p 다시보기): 방송 캐릭터 오버레이가 미니맵 아이콘 자리를 덮어
    로딩·선택 화면이 전부 "관전"으로 읽혔다 - 게임 시작에서 거꾸로 훑으면 로딩 화면 두 장에서
    포기해 선택 화면까지 못 갔다. 선택 화면 판독이 있으면 관전 판정으로 포기하지 않는다."""
    frames = [(0.0, _lobby_frame()), (3.0, _lobby_frame()), (6.0, _lobby_frame()), (9.0, _select_route_frame())]

    assert find_portraits_in_frames(frames, PROFILE) is not None


def test_empty_placeholder_cards_on_character_select_are_skipped():
    """실측(2026-09-30): 캐릭터 선택 화면에서는 팀원 칸이 회색 "EMPTY" 자리표시인데도 넓은 판정용
    칸이 주변 색 때문에 통과했다. 저장용 칸도 초상화다워야 받는다."""
    character_select = _with_select_header(_blank_frame())
    for base in ("portrait", "teammate1", "teammate2"):
        _paint(character_select, base, VIVID)
        _paint(character_select, f"{base}_display", DIM)
    route_select = _select_route_frame(me=(250, 30, 200))
    frames = [(0.0, character_select), (3.0, route_select)]

    found = find_portraits_in_frames(frames, PROFILE)

    assert found is not None
    assert tuple(found.me[0, 0]) == (250, 30, 200)


def test_1080p_profile_can_read_the_select_screen():
    profile = ResolutionProfile.for_resolution(1920, 1080)

    assert {"select_timer", "select_title", "select_mode"} <= set(profile.rois)
