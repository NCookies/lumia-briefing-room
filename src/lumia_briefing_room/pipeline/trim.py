"""클립 자르기: 고른 구간만 남기고 나머지는 지운다.

`-c copy` 로 잘라 재인코딩이 없다(빠르고 화질 손실이 없다). 시작이 키프레임이 아니어도 MP4 편집 리스트로 시작 프레임이
정확히 맞는다(실측: 5.5초 지점 프레임과 픽셀 차이 0.0). 대신 시작 앞의 키프레임까지(최대 3초)는 화면에 안 보이는 채로 파일에 남는다.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from lumia_briefing_room.config import ThumbnailConfig
from lumia_briefing_room.pipeline.clip import make_thumbnail

MIN_LENGTH_SEC = 1.0
END_TOLERANCE_SEC = 0.05


def validate_range(start: float, end: float, duration: float) -> None:
    if start < 0 or end <= start:
        raise ValueError("구간이 올바르지 않습니다")
    if end > duration + END_TOLERANCE_SEC:
        raise ValueError("끝 시각이 클립 길이를 넘을 수 없습니다")
    if end - start < MIN_LENGTH_SEC:
        raise ValueError(f"구간이 너무 짧습니다 (최소 {MIN_LENGTH_SEC:g}초)")


def trim_clip(
    meta_path: Path, start: float, end: float, *, ffmpeg_path: Path, thumbnail: ThumbnailConfig
) -> dict:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    duration = float(meta["durationSec"])
    validate_range(start, end, duration)
    end = min(end, duration)

    mp4 = meta_path.with_suffix(".mp4")
    tmp = meta_path.with_suffix(".trim.mp4")
    cmd = [
        str(ffmpeg_path), "-hide_banner", "-v", "error", "-y",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(mp4),
        "-map", "0", "-c", "copy", str(tmp),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        os.replace(tmp, mp4)
    finally:
        tmp.unlink(missing_ok=True)

    new_duration = round(end - start, 3)
    meta.setdefault("originalDurationSec", duration)
    meta["durationSec"] = new_duration
    meta["videoOffsetSec"] = round(float(meta.get("videoOffsetSec", 0.0)) + start, 3)
    meta["trimmed"] = True

    thumb = meta.get("thumbnailPath")
    if thumb:
        make_thumbnail(
            mp4, Path(thumb), duration_sec=new_duration, offset_ratio=thumbnail.offset_ratio,
            width=thumbnail.width, ffmpeg_path=ffmpeg_path,
        )

    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta
