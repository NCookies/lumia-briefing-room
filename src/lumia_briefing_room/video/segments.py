from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from lumia_briefing_room.video.session import RecordingSession

_CHUNK_PATTERN = re.compile(r"^chunk-stream(\d)-(\d{5})\.m4s$")


def segment_number_at(session: RecordingSession, t: datetime) -> int:
    """research.md §2.5: 세그먼트 N 시작(UTC) = 세션시작 + (N-1) * duration.
    역으로, 시각 t 가 속한 세그먼트 번호를 구한다 (1부터 시작).
    """
    offset = (t - session.start_utc).total_seconds()
    return int(offset // session.segment_duration_sec) + 1


@dataclass(frozen=True)
class SegmentRange:
    first: int
    last: int

    def numbers(self) -> list[int]:
        return list(range(self.first, self.last + 1))

    def gaps(self, existing: list[int]) -> list[tuple[int, int]]:
        """이 범위 안에서 existing 에 없는 번호들을 연속 구간으로 묶어 반환한다."""
        existing_set = set(existing)
        gaps: list[tuple[int, int]] = []
        gap_start: int | None = None
        for n in range(self.first, self.last + 1):
            if n in existing_set:
                if gap_start is not None:
                    gaps.append((gap_start, n - 1))
                    gap_start = None
            elif gap_start is None:
                gap_start = n
        if gap_start is not None:
            gaps.append((gap_start, self.last))
        return gaps


def segment_time_range(
    session: RecordingSession, start: datetime, end: datetime
) -> SegmentRange:
    if end < start:
        raise ValueError("end 가 start 보다 앞설 수 없다")
    first = segment_number_at(session, start)
    last = segment_number_at(session, end)
    return SegmentRange(first=first, last=last)


def existing_segment_numbers(
    session: RecordingSession, stream: int, first: int, last: int
) -> list[int]:
    """지정된 범위에서 실제로 존재하는(.tmp 가 아닌 완료된) 조각 번호를 오름차순으로 반환한다.

    research.md §1.6: 링버퍼가 실시간으로 지운다. "폴더가 있으니 조각도 있다"는
    가정은 틀린다 — 번호로 접근하기 전에 항상 존재를 확인해야 한다.
    """
    found: list[int] = []
    for path in session.directory.iterdir():
        m = _CHUNK_PATTERN.match(path.name)
        if not m:
            continue
        if int(m.group(1)) != stream:
            continue
        n = int(m.group(2))
        if first <= n <= last:
            found.append(n)
    return sorted(found)
