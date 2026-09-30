from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from lumia_briefing_room.detect.color import channel_stats, count, vivid_mask
from lumia_briefing_room.detect.select_screen import read_select_screen
from lumia_briefing_room.detect.spectator import read_spectating
from lumia_briefing_room.detect.types import PortraitCrops
from lumia_briefing_room.profiles.models import ResolutionProfile

PORTRAIT_VIVID_V_MIN = 80
PORTRAIT_VIVID_S_MIN = 25
PORTRAIT_VIVID_PCT_MIN = 10.0


def crop_portraits(frame: np.ndarray, profile: ResolutionProfile) -> PortraitCrops:
    """내 캐릭터·팀원 2명의 초상화를 저장용으로 넉넉하게 자른다(SPEC §2.10 좌표, `2.9` 표 동일).

    `*_display` ROI(`portrait_display`/`teammate1_display`/`teammate2_display`)는 얼굴만 딱
    잘리던 `portrait`/`teammate1`/`teammate2`(판정용, `crops_look_like_portraits` 전용) 보다
    위아래로 넉넉해 상반신까지 나온다(실측 2026-09-29, 사용자 피드백 - "얼굴만 잘라서 못생겨
    보인다"). 판정용 ROI 는 화면마다 그림이 채우는 비율이 달라(밝고 채도 높은 픽셀 비율로
    화면을 가리는지 본다) 넓히면 배경 여백이 늘어나 오히려 못 찾는 경기가 생겨 그대로 뒀다.
    """
    return PortraitCrops(
        me=profile.crop(frame, "portrait_display"),
        teammate1=profile.crop(frame, "teammate1_display"),
        teammate2=profile.crop(frame, "teammate2_display"),
    )


def _detect_crops(frame: np.ndarray, profile: ResolutionProfile) -> PortraitCrops:
    """`crops_look_like_portraits` 판정 전용 - 저장용(`crop_portraits`)보다 좁고 신뢰도가 검증된 ROI."""
    return PortraitCrops(
        me=profile.crop(frame, "portrait"),
        teammate1=profile.crop(frame, "teammate1"),
        teammate2=profile.crop(frame, "teammate2"),
    )


def _looks_like_portrait(rgb: np.ndarray) -> bool:
    """실측(2026-09-29): 캐릭터 그림은 밝고 채도 높은 픽셀이 일정 비율 이상이다.

    같은 화면 좌표라도 페이지(캐릭터 선택·루트 선택)에 따라 다른 내용이 그려질 수 있어
    한 칸만 보면 글자·아이콘에 오탐할 수 있다 - `crops_look_like_portraits` 가 3 칸을
    모두 요구해 이 오탐을 줄인다.
    """
    stats = channel_stats(rgb)
    mask = vivid_mask(stats, v_min=PORTRAIT_VIVID_V_MIN, s_min=PORTRAIT_VIVID_S_MIN)
    return (count(mask) / mask.size * 100) >= PORTRAIT_VIVID_PCT_MIN


PORTRAIT_TEXTURE_STD_MIN = 40.0


def _has_artwork_texture(rgb: np.ndarray) -> bool:
    """채도가 낮은 그림(흰 머리 캐릭터 등)도 채워진 칸으로 보는 기준: 밝기의 표준편차.

    실측(2026-10-01, 2560x1440): 채워진 카드 65~100, 회색 "EMPTY" 자리표시 19~24. 색 기준(채도 높은 픽셀 10%)은 흰 머리 카드가
    5.5% 라 놓쳤고, 자리표시(4.4~6.1%)와는 색으로 가를 수도 없었다.
    """
    return float(rgb.mean(axis=2).std()) >= PORTRAIT_TEXTURE_STD_MIN


def _looks_filled(rgb: np.ndarray) -> bool:
    return _looks_like_portrait(rgb) or _has_artwork_texture(rgb)


def crops_look_filled(crops: PortraitCrops) -> bool:
    return _looks_filled(crops.me) and _looks_filled(crops.teammate1) and _looks_filled(crops.teammate2)


def crops_look_like_portraits(crops: PortraitCrops) -> bool:
    return (
        _looks_like_portrait(crops.me)
        and _looks_like_portrait(crops.teammate1)
        and _looks_like_portrait(crops.teammate2)
    )


GIVE_UP_AFTER_CONSECUTIVE_NON_NONE = 2
SELECT_SCREEN_ROIS = ("select_timer", "select_title")


def _portraits_if_filled(frame: np.ndarray, profile: ResolutionProfile, *, texture: bool = False) -> PortraitCrops | None:
    """판정용 칸과 저장용 칸이 둘 다 초상화다워야 받는다.

    실측(2026-09-30): 캐릭터 선택 화면에서는 팀원 칸이 회색 "EMPTY" 자리표시인데도 넓은 판정용
    칸이 주변 색 때문에 통과했다 - 저장용 칸까지 보면 루트 선택 화면(세 장 다 채워짐)만 남는다.
    """
    check = crops_look_filled if texture else crops_look_like_portraits
    if not check(_detect_crops(frame, profile)):
        return None
    crops = crop_portraits(frame, profile)
    return crops if check(crops) else None


def _find_on_select_screens(
    frames: Iterable[tuple[float, np.ndarray]], profile: ResolutionProfile
) -> PortraitCrops | None:
    """캐릭터·루트 선택 화면 머리띠(`detect/select_screen.py`)가 보이는 프레임에서만 찾는다.

    실측(2026-09-30, 치지직 1080p 다시보기): 방송 캐릭터 오버레이가 미니맵 아이콘 자리를 덮어
    로딩·선택 화면이 전부 "관전"으로 읽혀, 관전 판정으로 포기하는 옛 방식은 선택 화면까지 가지
    못했다. 머리띠는 상단 가운데·좌상단이라 오버레이에 덜 가리고, 선택 화면에서만 보므로 이전
    경기의 로비·인게임 화면을 잘못 잡을 걱정이 없어 포기 규칙도 필요 없다.
    """
    for _, frame in frames:
        if not read_select_screen(profile.crop(frame, "select_timer"), profile.crop(frame, "select_title")):
            continue
        found = _portraits_if_filled(frame, profile, texture=True)
        if found is not None:
            return found
    return None


def find_portraits_in_frames(
    frames: Iterable[tuple[float, np.ndarray]], profile: ResolutionProfile
) -> PortraitCrops | None:
    """경기 시작 전후 루트 선택 화면(우측 아래 팀원 카드 3장)에서 초상화를 자른다.

    실측(2026-09-29): 애초에 노렸던 "관전 판정 True(=팀 로비 원형 화면)" 프레임은 화면에
    떠 있는 시간이 3초 키프레임 간격보다 짧아 실전에서 거의 못 잡았고, 좌표도 팀 소개
    화면이 아니라 게임 화면 하단 자기 HUD 를 가리키고 있었다(우연히 그 프레임에서만
    사람 얼굴처럼 보였을 뿐). 대신 관전 판정이 아직 `None`(미니맵도 안 보이는 로비·선택
    단계)인 동안 매 프레임에서 `portrait`/`teammate1`/`teammate2` 세 칸을 직접 확인해,
    셋 다 초상화다운 색(`crops_look_like_portraits`)이면 그 자리에서 멈춘다.

    재실측(2026-09-29, 같은 날 후속): `pipeline/portrait_scan.py` 가 `matchStartUtc` 앞뒤로
    훑다 보니, 훑는 구간 맨 앞쪽이 이전 경기의 팀 로비·인게임 꼬리일 수 있다 - 그 한두 프레임
    때문에 바로 포기하면 정작 이 경기의 루트 선택 화면(그 바로 뒤에 있을 수 있다)을 못 본다.
    그래서 `None` 이 아닌 판정이 **연속으로** `GIVE_UP_AFTER_CONSECUTIVE_NON_NONE` 번 나와야
    포기한다 - 낱개로 섞인 오판(관전 판정 자체가 가끔 틀리는 것도 실측으로 확인함)은 넘기고,
    진짜로 로비·인게임에 들어선 뒤(연속으로 찍힘)에는 더 볼 필요가 없어 계속 멈춘다.

    프로필에 선택 화면 칸이 있으면(2026-09-30 이후 2560x1440·1920x1080) 위 관전 판정 대신
    `_find_on_select_screens` 를 쓴다. 관전 판정 방식은 선택 화면 칸이 없는 프로필용으로 남긴다.
    """
    if all(name in profile.rois for name in SELECT_SCREEN_ROIS):
        return _find_on_select_screens(frames, profile)

    consecutive_non_none = 0
    for _, frame in frames:
        spectating = read_spectating(
            profile.crop(frame, "minimap_icons"), profile.crop(frame, "hp_strip")
        )
        if spectating is not None:
            consecutive_non_none += 1
            if consecutive_non_none >= GIVE_UP_AFTER_CONSECUTIVE_NON_NONE:
                return None
            continue
        consecutive_non_none = 0
        found = _portraits_if_filled(frame, profile)
        if found is not None:
            return found
    return None
