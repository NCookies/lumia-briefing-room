from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from lumia_briefing_room.detect.color import channel_stats, count, vivid_mask
from lumia_briefing_room.detect.spectator import read_spectating
from lumia_briefing_room.detect.types import PortraitCrops
from lumia_briefing_room.profiles.models import ResolutionProfile

PORTRAIT_VIVID_V_MIN = 80
PORTRAIT_VIVID_S_MIN = 25
PORTRAIT_VIVID_PCT_MIN = 10.0


def crop_portraits(frame: np.ndarray, profile: ResolutionProfile) -> PortraitCrops:
    """내 캐릭터·팀원 2명의 초상화 ROI 를 그대로 자른다(SPEC §2.10 좌표, `2.9` 표 동일)."""
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


def crops_look_like_portraits(crops: PortraitCrops) -> bool:
    return (
        _looks_like_portrait(crops.me)
        and _looks_like_portrait(crops.teammate1)
        and _looks_like_portrait(crops.teammate2)
    )


def find_portraits_in_frames(
    frames: Iterable[tuple[float, np.ndarray]], profile: ResolutionProfile
) -> PortraitCrops | None:
    """경기 시작 직후 루트 선택 화면(우측 아래 팀원 카드 3장)에서 초상화를 자른다.

    실측(2026-09-29): 애초에 노렸던 "관전 판정 True(=팀 로비 원형 화면)" 프레임은 화면에
    떠 있는 시간이 3초 키프레임 간격보다 짧아 실전에서 거의 못 잡았고, 좌표도 팀 소개
    화면이 아니라 게임 화면 하단 자기 HUD 를 가리키고 있었다(우연히 그 프레임에서만
    사람 얼굴처럼 보였을 뿐). 대신 관전 판정이 아직 `None`(미니맵도 안 보이는 로비·선택
    단계)인 동안 매 프레임에서 `portrait`/`teammate1`/`teammate2` 세 칸을 직접 확인해,
    셋 다 초상화다운 색(`crops_look_like_portraits`)이면 그 자리에서 멈춘다. `None` 을
    벗어나면(`True`=팀 로비, `False`=실제 인게임) 루트 선택 화면은 이미 지나친 것이라
    포기한다 - 그 뒤엔 이 좌표에 다른 HUD 가 그려진다.
    """
    for _, frame in frames:
        spectating = read_spectating(
            profile.crop(frame, "minimap_icons"), profile.crop(frame, "hp_strip")
        )
        if spectating is not None:
            return None
        crops = crop_portraits(frame, profile)
        if crops_look_like_portraits(crops):
            return crops
    return None
