import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from enum import Enum

# research.md §3.1, SPEC §2.3: 매치 경계 마커. 클래스/메서드/라인번호는 버전에 따라
# 바뀔 수 있어 이 리터럴 문자열만 본다.
MATCH_START_MARKER = "[PROFILE TIME][LOADING][GAME]"
MATCH_END_MARKER = "[PROFILE TIME][LOADING][LOBBY]"
# 캐릭터 선택은 로비 장면에서 하므로 [LOADING][GAME] 보다 앞선다(plan-fullvideo §3.8).
START_MATCHING_MARKER = "matchingNotification : StartMatching"
MATCHING_COMPLETE_MARKER = "MatchingComplete, matchPadding.userCount"
PRACTICE_INFO_MARKER = '"matchingMode":"Practice"'
# 캐릭터 선택~로딩 실측 약 80초. 이보다 훨씬 앞선 MatchingComplete 는 이 게임의 것이 아니다.
MAX_SELECT_LEAD = timedelta(minutes=5)

_SET_MODE_RE = re.compile(r"GlobalUserData:SetMatchingMode:\d+\]\s+Invoked:\s*(\w+)")

_TIMESTAMP_RE = re.compile(r"^\[\w+\]\[[^\]]*\]\[([\d-]+ [\d:,]+)\]\[\d+\]\[[^\]]*\]")
_TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S,%f"


class LogEventType(str, Enum):
    MATCH_START = "match_start"
    MATCH_END = "match_end"


@dataclass(frozen=True)
class LogEvent:
    type: LogEventType
    local_time: datetime


def _parse_local_timestamp(line: str) -> datetime | None:
    m = _TIMESTAMP_RE.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), _TIMESTAMP_FMT)
    except ValueError:
        return None


def parse_line(line: str) -> LogEvent | None:
    """Player.log 한 줄에서 매치 시작/종료 이벤트를 읽는다. (research §3.3)"""
    if MATCH_START_MARKER in line:
        t = _parse_local_timestamp(line)
        return LogEvent(LogEventType.MATCH_START, t) if t else None
    if MATCH_END_MARKER in line:
        t = _parse_local_timestamp(line)
        return LogEvent(LogEventType.MATCH_END, t) if t else None
    return None


@dataclass(frozen=True)
class MatchBoundary:
    """`start_utc` 는 풀영상 시작(캐릭터 선택 화면), `loading_utc` 는 `[LOADING][GAME]` 시각이다."""

    start_utc: datetime
    end_utc: datetime | None  # None = 아직 로그에 종료가 안 찍힘(진행 중)
    loading_utc: datetime | None = None

    def __post_init__(self) -> None:
        if self.loading_utc is None:
            object.__setattr__(self, "loading_utc", self.start_utc)


def _to_utc(local_time: datetime, local_tz: tzinfo) -> datetime:
    return local_time.replace(tzinfo=local_tz).astimezone(timezone.utc)


def extract_matches(lines: Iterable[str], *, local_tz: tzinfo) -> list[MatchBoundary]:
    """로그 라인들에서 게임 경계 목록을 뽑는다. (plan-fullvideo §3.8, SPEC §7.2.1 백로그 복구가 이걸 쓴다)

    - 시작 = `[LOADING][GAME]` 직전의 마지막 `MatchingComplete`(캐릭터 선택 시작). 그 사이에
      `StartMatching` 이 다시 있으면 앞의 것은 닷지라 버린다. 없으면 `[LOADING][GAME]` 이 시작이다.
    - 연습 모드(`Practice`)는 게임이 아니라 뺀다. 사용자 설정 게임은 넣는다.
    - 로그가 매치 도중에 시작해 시작 없이 종료만 있으면 그 종료는 무시한다.
    - 마지막 시작에 대응하는 종료가 아직 없으면 end_utc=None 으로 남긴다.
    """
    matches: list[MatchBoundary] = []
    pending_complete: datetime | None = None
    last_mode: str | None = None
    open_game: tuple[datetime, datetime, bool] | None = None  # (start, loading, practice)

    def close(end: datetime | None) -> None:
        nonlocal open_game
        if open_game is None:
            return
        start, loading, practice = open_game
        open_game = None
        if not practice:
            matches.append(
                MatchBoundary(
                    start_utc=_to_utc(start, local_tz),
                    end_utc=_to_utc(end, local_tz) if end else None,
                    loading_utc=_to_utc(loading, local_tz),
                )
            )

    for line in lines:
        if PRACTICE_INFO_MARKER in line:
            if open_game is not None:
                open_game = (open_game[0], open_game[1], True)
            continue
        m = _SET_MODE_RE.search(line)
        if m:
            last_mode = m.group(1)
            continue
        if START_MATCHING_MARKER in line:
            pending_complete = None
            continue
        if MATCHING_COMPLETE_MARKER in line:
            pending_complete = _parse_local_timestamp(line) or pending_complete
            continue
        event = parse_line(line)
        if event is None:
            continue
        if event.type is LogEventType.MATCH_START:
            start = event.local_time
            if pending_complete is not None and timedelta(0) <= start - pending_complete <= MAX_SELECT_LEAD:
                start = pending_complete
            open_game = (start, event.local_time, last_mode == "Practice")
            pending_complete = None
        elif event.type is LogEventType.MATCH_END:
            close(event.local_time)
            last_mode = None
            pending_complete = None

    close(None)
    return matches
