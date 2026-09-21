import os
import re
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from enum import Enum
from pathlib import Path

# research.md §3.1, SPEC §2.3: 매치 경계 마커. 클래스/메서드/라인번호는 버전에 따라
# 바뀔 수 있어 이 리터럴 문자열만 본다.
MATCH_START_MARKER = "[PROFILE TIME][LOADING][GAME]"
MATCH_END_MARKER = "[PROFILE TIME][LOADING][LOBBY]"

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
    start_utc: datetime
    end_utc: datetime | None  # None = 아직 로그에 종료가 안 찍힘(진행 중)


def _to_utc(local_time: datetime, local_tz: tzinfo) -> datetime:
    return local_time.replace(tzinfo=local_tz).astimezone(timezone.utc)


def extract_matches(lines: Iterable[str], *, local_tz: tzinfo) -> list[MatchBoundary]:
    """로그 라인들에서 매치 경계 목록을 뽑는다. (SPEC §2.3, §7.2.1 백로그 복구가 이걸 쓴다)

    - 로그가 매치 도중에 시작해 시작 없이 종료만 있으면 그 종료는 무시한다
      (시작을 모르는 매치는 처리할 수 없다).
    - 마지막 시작에 대응하는 종료가 아직 없으면 end_utc=None 으로 남긴다.
    """
    matches: list[MatchBoundary] = []
    pending_start: datetime | None = None

    for line in lines:
        event = parse_line(line)
        if event is None:
            continue
        if event.type is LogEventType.MATCH_START:
            pending_start = event.local_time
        elif event.type is LogEventType.MATCH_END and pending_start is not None:
            matches.append(
                MatchBoundary(
                    start_utc=_to_utc(pending_start, local_tz),
                    end_utc=_to_utc(event.local_time, local_tz),
                )
            )
            pending_start = None

    if pending_start is not None:
        matches.append(MatchBoundary(start_utc=_to_utc(pending_start, local_tz), end_utc=None))

    return matches


def tail_follow(
    path: Path,
    *,
    start_at_end: bool = True,
    poll_interval_sec: float = 1.0,
    should_stop: Callable[[], bool] = lambda: False,
) -> Iterator[str]:
    """파일을 계속 지켜보며 새로 추가되는 줄을 낸다(`tail -f`).

    `should_stop()` 이 참이 되면 유휴 대기(새 줄이 없을 때) 중에 멈춘다 — 이미
    파일에 남아있는 줄은 멈추기 전에 마저 낸다. 기본값(`lambda: False`)이면
    끝나지 않는 제너레이터다 (plan-pipeline.md §3-5: 트레이 감시 정지/재개 배선).

    파일을 계속 열어 두지 않고 읽을 때만 열어 위치(바이트)를 기억한다. 게임이 다시 실행되면 `Player.log` 가
    새 파일로 바뀌거나 비워지는데, 처음 연 핸들을 쥐고 있으면 옛 파일 끝만 보고 새 경기를 영영 못 본다.
    파일이 바뀌었거나(ID 변경) 줄어들었으면 처음부터 다시 읽는다.

    처음 위치는 호출 시점에 즉시 정한다. 제너레이터 함수로 통째로 만들면 본문이 첫 next() 호출까지
    미뤄져, 그 사이 파일에 쓰인 내용을 `start_at_end=True` 가 건너뛰어버리는 경쟁 상태가 생긴다.
    """
    stat = os.stat(path)
    position = stat.st_size if start_at_end else 0
    return _follow(path, position, _identity(stat), poll_interval_sec, should_stop)


def _identity(stat: os.stat_result) -> tuple[int, int]:
    return stat.st_dev, stat.st_ino


def _follow(
    path: Path, position: int, identity: tuple[int, int], poll_interval_sec: float, should_stop: Callable[[], bool]
) -> Iterator[str]:
    pending = b""
    while True:
        try:
            stat = os.stat(path)
        except OSError:
            stat = None
        if stat is not None:
            if _identity(stat) != identity or stat.st_size < position:
                position, pending, identity = 0, b"", _identity(stat)
            if stat.st_size > position:
                try:
                    with open(path, "rb") as f:
                        f.seek(position)
                        data = f.read()
                except OSError:
                    data = b""
                position += len(data)
                pending += data
                *complete, pending = pending.split(b"\n")
                if complete:
                    for raw in complete:
                        yield raw.decode("utf-8", errors="replace").rstrip("\r") + "\n"
                    continue
        if should_stop():
            return
        time.sleep(poll_interval_sec)
