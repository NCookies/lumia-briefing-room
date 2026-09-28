from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from lumia_briefing_room.detect.spectator import read_spectating
from lumia_briefing_room.detect.types import PortraitCrops
from lumia_briefing_room.profiles.models import ResolutionProfile


def crop_portraits(frame: np.ndarray, profile: ResolutionProfile) -> PortraitCrops:
    """내 캐릭터·팀원 2명의 초상화 ROI 를 그대로 자른다(SPEC §2.10 좌표, `2.9` 표 동일)."""
    return PortraitCrops(
        me=profile.crop(frame, "portrait"),
        teammate1=profile.crop(frame, "teammate1"),
        teammate2=profile.crop(frame, "teammate2"),
    )


def find_portraits_in_frames(
    frames: Iterable[tuple[float, np.ndarray]], profile: ResolutionProfile
) -> PortraitCrops | None:
    """경기 시작 직후 팀 소개 화면(미니맵 헤더는 있고 체력바는 없음, `spectating=True`)에서 초상화를 자른다.

    로딩 화면(`spectating=None`, 미니맵조차 안 보임)은 건너뛰고, 팀 소개 화면을 만나면 바로 멈춘다.
    체력바가 있는(`spectating=False`) 인게임 화면이 먼저 나오면 팀 소개 화면을 이미 지나친 것이라
    포기한다 - 그 뒤엔 초상화 UI 가 HUD 로 바뀌어 있어 이 ROI 로는 깨끗한 초상화를 못 얻는다.
    """
    for _, frame in frames:
        spectating = read_spectating(
            profile.crop(frame, "minimap_icons"), profile.crop(frame, "hp_strip")
        )
        if spectating is True:
            return crop_portraits(frame, profile)
        if spectating is False:
            return None
    return None
