from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_FOLDER_PATTERN = re.compile(r"^bg_(\d+)_(\d{8})_(\d{6})$")
_ISO_DURATION_PATTERN = re.compile(
    r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>[\d.]+)S)?$"
)


class SessionParseError(Exception):
    """세션 폴더/session.mpd 를 해석할 수 없을 때."""


def _parse_iso_duration_minutes(text: str) -> float:
    m = _ISO_DURATION_PATTERN.match(text)
    if not m:
        raise SessionParseError(f"ISO8601 duration 형식이 아니다: {text!r}")
    hours = float(m.group("hours") or 0)
    minutes = float(m.group("minutes") or 0)
    seconds = float(m.group("seconds") or 0)
    return hours * 60 + minutes + seconds / 60


def _parse_folder_name(folder_name: str) -> tuple[int, datetime]:
    m = _FOLDER_PATTERN.match(folder_name)
    if not m:
        raise SessionParseError(f"세션 폴더명 패턴이 아니다: {folder_name!r}")
    app_id = int(m.group(1))
    dt = datetime.strptime(m.group(2) + m.group(3), "%Y%m%d%H%M%S").replace(
        tzinfo=timezone.utc
    )
    return app_id, dt


@dataclass(frozen=True)
class RecordingSession:
    """녹화 세션 하나(bg_<appid>_<YYYYMMDD>_<HHMMSS> 폴더)의 메타데이터.

    research.md §2.5: 세션시작(UTC) = session.mpd 의 availabilityStartTime
    (녹화 중, type="dynamic") 또는 폴더명(항상 유효).
    """

    directory: Path
    app_id: int
    start_utc: datetime
    width: int
    height: int
    segment_duration_sec: float
    buffer_minutes: float | None

    @classmethod
    def load(cls, directory: Path) -> "RecordingSession":
        app_id, folder_start_utc = _parse_folder_name(directory.name)

        mpd_path = directory / "session.mpd"
        if not mpd_path.exists():
            raise SessionParseError(f"session.mpd 가 없다: {mpd_path}")

        try:
            root = ET.fromstring(mpd_path.read_text(encoding="utf-8"))
        except ET.ParseError as exc:
            raise SessionParseError(f"session.mpd 파싱 실패: {exc}") from exc

        availability_start = root.get("availabilityStartTime")
        if availability_start:
            start_utc = datetime.strptime(
                availability_start, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
        else:
            start_utc = folder_start_utc

        adaptation_set = root.find(".//{*}AdaptationSet[@contentType='video']")
        if adaptation_set is None:
            raise SessionParseError("video AdaptationSet 을 찾을 수 없다")
        width = int(adaptation_set.get("maxWidth"))
        height = int(adaptation_set.get("maxHeight"))

        segment_template = adaptation_set.find(".//{*}SegmentTemplate")
        if segment_template is None:
            raise SessionParseError("SegmentTemplate 을 찾을 수 없다")
        timescale = int(segment_template.get("timescale"))
        duration_units = int(segment_template.get("duration"))
        segment_duration_sec = duration_units / timescale

        buffer_depth = root.get("timeShiftBufferDepth")
        buffer_minutes = (
            _parse_iso_duration_minutes(buffer_depth) if buffer_depth else None
        )

        return cls(
            directory=directory,
            app_id=app_id,
            start_utc=start_utc,
            width=width,
            height=height,
            segment_duration_sec=segment_duration_sec,
            buffer_minutes=buffer_minutes,
        )
