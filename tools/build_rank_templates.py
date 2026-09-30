"""결과 화면 순위 숫자(`3/7` 의 3) 본보기를 만든다.

usage:
    python tools/build_rank_templates.py <output.npz> --profile 2560x1440 3=frame_a.png 3=frame_b.png 1=frame_c.png

`숫자=결과 화면 전체 프레임 PNG` 를 여러 개 준다. 같은 숫자는 평균 낸다. 표본이 생긴 숫자를 추가할 때는 기존 npz 의 숫자도
다시 넣어야 한다(덮어쓴다).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lumia_briefing_room.detect.region import (  # noqa: E402
    build_region_template,
    region_score,
    save_region_templates,
)
from lumia_briefing_room.profiles.models import ResolutionProfile  # noqa: E402


def build_rank_templates(samples: dict[str, list[np.ndarray]], profile: ResolutionProfile) -> dict[str, np.ndarray]:
    return {
        digit: build_region_template([region_score(profile.crop(frame, "result_rank")) for frame in frames])
        for digit, frames in samples.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--profile", required=True, help="예: 2560x1440")
    parser.add_argument("samples", nargs="+", help="숫자=프레임.png")
    args = parser.parse_args()

    width, _, height = args.profile.partition("x")
    profile = ResolutionProfile.for_resolution(int(width), int(height))
    samples: dict[str, list[np.ndarray]] = {}
    for item in args.samples:
        digit, _, path = item.partition("=")
        if not digit.isdigit() or not path:
            raise SystemExit(f"형식은 숫자=파일.png 입니다: {item}")
        samples.setdefault(digit, []).append(np.array(Image.open(path).convert("RGB")))

    templates = build_rank_templates(samples, profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_region_templates(templates, args.output)
    for digit in sorted(templates):
        print(f"순위 {digit}: 표본 {len(samples[digit])}장, 폭 {templates[digit].shape[1]}")


if __name__ == "__main__":
    main()
