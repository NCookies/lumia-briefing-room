"""스팀 녹화가 게임 전·도중에 멈춰 녹화가 없거나 잘린 게임을 알아본다.

스팀은 프레임이 2초 넘게 밀리면 녹화 세션을 오류로 끝내고 게임을 다시 켤 때까지 새로 녹화하지 않는다
(`Steam\\logs\\streaming_log.txt`: "Ending game recording session due to error"). 그 뒤의 게임은 끝난 세션을
기준으로 처리돼 세그먼트가 하나도 없거나(전) 멈춘 지점까지만 있다(도중).
"""

from __future__ import annotations

import re
from datetime import datetime

from lumia_briefing_room.video.segments import SegmentRange

STOPPED_BEFORE_MESSAGE = (
    "스팀 녹화가 이 게임 전에 멈춰(스팀 녹화 오류) 녹화된 영상이 없어 분석하지 못했습니다. "
    "스팀 녹화는 게임을 다시 켜야 다시 시작됩니다."
)
STOPPED_DURING_MESSAGE = (
    "스팀 녹화가 게임 도중 멈춰(스팀 녹화 오류) 멈추기 전까지만 녹화·분석됐습니다. "
    "스팀 녹화는 게임을 다시 켜야 다시 시작됩니다."
)
# 게임이 끝나자마자 처리하면 마지막 몇 조각은 아직 안 써졌을 수 있다(3초 조각 3개).
END_TOLERANCE_SEGMENTS = 3
_OLD_MISSING_PREFIX = "세그먼트를 찾을 수 없다"
_CHUNK = re.compile(r"^chunk-stream0-(\d{5})\.m4s$")


def _last_chunk_number(directory) -> int | None:
    try:
        numbers = [int(m.group(1)) for p in directory.iterdir() if (m := _CHUNK.match(p.name))]
    except OSError:
        return None
    return max(numbers) if numbers else None


def recording_stop(session, seg_range: SegmentRange) -> str | None:
    """"before"(게임 시작 전에 녹화가 끝남) / "during"(게임 도중 끝남) / None."""
    last = _last_chunk_number(session.directory)
    if last is None or last < seg_range.first:
        return "before"
    if last < seg_range.last - END_TOLERANCE_SEGMENTS:
        return "during"
    return None


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def stopped_of_record(game: dict) -> str | None:
    """게임 기록(`game.json`)에서 읽는다. 표시가 없는 옛 기록은 오류 문구·풀영상 끝 조각으로 어림한다."""
    flag = game.get("recordingStopped")
    if flag in ("before", "during"):
        return flag
    if (game.get("source") or "steam") != "steam":
        return None
    video = game.get("fullVideo")
    if video is None:
        return "before" if (game.get("fullVideoError") or "").startswith(_OLD_MISSING_PREFIX) else None
    try:
        duration = float(video["segmentDurationSec"])
        elapsed = (_utc(game["matchEndUtc"]) - _utc(game["sessionStartUtc"])).total_seconds()
        expected_last = int(elapsed // duration) + 1
        end = int(video["segmentEnd"])
    except (KeyError, TypeError, ValueError):
        return None
    return "during" if end < expected_last - END_TOLERANCE_SEGMENTS else None


def error_of_record(game: dict) -> str | None:
    if stopped_of_record(game) == "before":
        return STOPPED_BEFORE_MESSAGE
    return game.get("fullVideoError")
