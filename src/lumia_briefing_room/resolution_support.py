"""녹화 해상도가 지원 범위인지 판정한다. (plan-deploy.md D3, §6)"""

from dataclasses import dataclass

from lumia_briefing_room.profiles.models import measured_resolutions

RATIO_16_9 = 16 / 9
RATIO_TOLERANCE = 0.01


@dataclass(frozen=True)
class ResolutionSupport:
    width: int
    height: int
    kind: str
    message: str


def classify_resolution(width: int, height: int) -> ResolutionSupport:
    size = f"{width}x{height}"
    if (width, height) in measured_resolutions():
        return ResolutionSupport(width, height, "measured", f"{size} — 측정한 해상도라 그대로 지원합니다.")
    if height and abs(width / height - RATIO_16_9) <= RATIO_TOLERANCE:
        return ResolutionSupport(
            width, height, "scaled",
            f"{size} — 16:9 라서 측정한 해상도(2560x1440)를 비율에 맞춰 조정해 대응합니다. 판독이 틀리면 알려 주세요.",
        )
    return ResolutionSupport(
        width, height, "unsupported_ratio",
        f"{size} — 16:9 가 아닌 화면 비율이라 정확도를 보장하지 못합니다. 클립은 만들어지지만 K/A·지역명 판독이 틀릴 수 있습니다.",
    )
