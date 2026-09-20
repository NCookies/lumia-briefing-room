"""실시간 Player.log 감시 + 백로그 복구. (SPEC §7.2, §7.2.1)

`run_once`/`run_forever` 는 실제 I/O(ffmpeg 호출, 파일 시스템 감시)를 직접 하지
않는다 — `process` 콜백과 `now`/`sleep` 을 주입받는다. 그래야 무한루프·실시간
지연 없이 테스트할 수 있다. 진짜 배선(실제 tail_follow, 실제 process_match 호출)은
`cli/watch.py` 가 맡는다.
"""

import json
import re
import shutil
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from pathlib import Path

from lumia_briefing_room.config import Config
from lumia_briefing_room.pipeline.playerlog import (
    LogEventType,
    MatchBoundary,
    extract_matches,
    parse_line,
)
from lumia_briefing_room.steam_paths import find_steam_install_path, read_buffer_minutes_override
from lumia_briefing_room.video.segments import SegmentRange
from lumia_briefing_room.video.session import RecordingSession, SessionParseError

_BG_FOLDER_APPID_RE = re.compile(r"^bg_(\d+)_")


def remaining_margin_minutes(match_start_utc: datetime, now_utc: datetime, buffer_minutes: float) -> float:
    """SPEC §7.2.1: 매치의 첫 세그먼트 나이 = now - 매치시작. 남은 여유 = 버퍼 - 나이."""
    age_min = (now_utc - match_start_utc).total_seconds() / 60
    return buffer_minutes - age_min


def should_rescue(remaining_margin_min: float, threshold_min: float) -> bool:
    """SPEC §7.2.1 구출 정책: 남은 여유가 임계 이하면 원본을 먼저 통째로 복사한다."""
    return remaining_margin_min <= threshold_min


def match_key(match: MatchBoundary) -> str:
    return match.start_utc.isoformat()


@dataclass(frozen=True)
class ProcessedState:
    """이미 처리한 매치 목록. SPEC §7.2.1 백로그 복구가 "이미 처리한 매치는 건너뛴다"에 쓴다."""

    processed_keys: frozenset[str]

    @classmethod
    def load(cls, path: Path) -> "ProcessedState":
        if not path.exists():
            return cls(frozenset())
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(frozenset(data.get("processed", [])))

    def with_added(self, key: str) -> "ProcessedState":
        return ProcessedState(self.processed_keys | {key})

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"processed": sorted(self.processed_keys)}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def unprocessed_matches(matches: list[MatchBoundary], state: ProcessedState) -> list[MatchBoundary]:
    """처리 이력에 없고, 끝난(end_utc 있는) 매치만 남긴다. 진행 중인 매치는 아직 대상이 아니다."""
    return [
        m for m in matches
        if m.end_utc is not None and match_key(m) not in state.processed_keys
    ]


def discover_backlog(
    player_log: Path, player_prev_log: Path | None, *, local_tz: tzinfo
) -> list[MatchBoundary]:
    """SPEC §7.2.1: Player-prev.log + Player.log 를 순서대로 읽어 매치 경계를 뽑는다.

    Player-prev.log 는 이전 세션 전체, Player.log 는 현재 세션 전체라 파일
    순서 자체가 이미 시간 순이다(interleave 불필요) — research §3.1.
    """
    lines: list[str] = []
    if player_prev_log is not None and player_prev_log.exists():
        lines += player_prev_log.read_text(encoding="utf-8", errors="replace").splitlines()
    if not player_log.exists():
        return []
    lines += player_log.read_text(encoding="utf-8", errors="replace").splitlines()
    return extract_matches(lines, local_tz=local_tz)


def find_session_for_time(recording_root: Path, t: datetime) -> Path | None:
    """t 시각을 포함할 만한 세션 폴더를 찾는다.

    `recording_root` 아래 `bg_*` 폴더들을 훑어 start_utc <= t 인 것 중
    가장 늦게 시작한 것을 고른다(세션은 겹치지 않는다고 가정, SPEC §2.4).
    """
    candidates: list[RecordingSession] = []
    for entry in recording_root.iterdir():
        if not entry.is_dir() or not entry.name.startswith("bg_"):
            continue
        try:
            session = RecordingSession.load(entry)
        except SessionParseError:
            continue
        if session.start_utc <= t:
            candidates.append(session)

    if not candidates:
        return None
    return max(candidates, key=lambda s: s.start_utc).directory


def resolve_buffer_minutes(
    cfg: Config, recording_root: Path, *, steam_path: Path | None = None
) -> float:
    """SPEC §2.6: session.mpd -> localconfig.vdf -> 120분 기본값. (plan-pipeline.md §3-4)

    현재 녹화 중인(dynamic) 세션이 있으면 거기서 읽는다. 없으면 남아있는 세션
    폴더 이름에서라도 appid 를 뽑아 `localconfig.vdf` 의 게임별 설정(`PerGameSettings.
    <appid>.minutes`)을 찾는다. 그것도 없으면(스팀 미설치, 세션 폴더가 하나도
    없음, 게임별 설정 자체가 없음) 120분 기본값으로 떨어진다.
    """
    if cfg.watch.buffer_minutes != "auto":
        return float(cfg.watch.buffer_minutes)

    app_id: int | None = None
    if recording_root.exists():
        for entry in recording_root.iterdir():
            if not entry.is_dir():
                continue
            m = _BG_FOLDER_APPID_RE.match(entry.name)
            if not m:
                continue
            app_id = app_id if app_id is not None else int(m.group(1))
            try:
                session = RecordingSession.load(entry)
            except SessionParseError:
                continue
            if session.buffer_minutes is not None:
                return session.buffer_minutes

    if app_id is not None:
        resolved_steam_path = steam_path if steam_path is not None else find_steam_install_path()
        if resolved_steam_path is not None:
            minutes = read_buffer_minutes_override(resolved_steam_path, str(app_id))
            if minutes is not None:
                return minutes

    return 120.0


def rescue_copy(
    session: RecordingSession,
    seg_range: SegmentRange,
    dest_root: Path,
    *,
    stream_video: int = 0,
    stream_audio: int = 1,
) -> Path:
    """SPEC §7.2.1 구출 정책: 원본 세그먼트를 통째로 tmp 로 복사한다.

    분석 도중 링버퍼가 원본을 지워도 되도록, session.mpd + init + 존재하는
    세그먼트를 그대로 복사해 RecordingSession.load() 로 다시 읽을 수 있는
    독립된 폴더를 만든다.

    목적지 폴더 이름은 원본과 **똑같이** `bg_<appid>_<날짜>_<시각>` 를 유지한다 —
    RecordingSession.load() 가 폴더명 자체에서 appid/시작시각을 읽기 때문에
    다른 이름을 붙이면 다시 로드할 수 없다. 격리는 `dest_root` 로 한다.
    """
    dest = dest_root / session.directory.name
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(session.directory / "session.mpd", dest / "session.mpd")

    for stream in (stream_video, stream_audio):
        init_src = session.directory / f"init-stream{stream}.m4s"
        if init_src.exists():
            shutil.copy2(init_src, dest / init_src.name)
        for n in seg_range.numbers():
            src = session.directory / f"chunk-stream{stream}-{n:05d}.m4s"
            if src.exists():
                shutil.copy2(src, dest / src.name)

    return dest


ProcessCallback = Callable[[Path, MatchBoundary, bool], None]


def run_once(
    matches: list[MatchBoundary],
    state: ProcessedState,
    *,
    recording_root: Path,
    now: Callable[[], datetime],
    rescue_threshold_min: float,
    buffer_minutes: float,
    process: ProcessCallback,
    state_path: Path,
) -> ProcessedState:
    """SPEC §7.2.1 백로그 복구: 처리 안 된 매치를 오래된 것부터 처리한다.

    세션을 못 찾으면(소실) 건너뛰고 처리 이력에도 남기지 않는다 — 나중에
    세션이 나타날 리는 없지만, 최소한 "처리했다고 잘못 기록"하지는 않는다.
    """
    for m in unprocessed_matches(matches, state):
        session_dir = find_session_for_time(recording_root, m.start_utc)
        if session_dir is None:
            continue

        margin = remaining_margin_minutes(m.start_utc, now(), buffer_minutes)
        process(session_dir, m, should_rescue(margin, rescue_threshold_min))

        state = state.with_added(match_key(m))
        state.save(state_path)

    return state


def run_forever(
    lines: Iterable[str],
    *,
    local_tz: tzinfo,
    recording_root: Path,
    now: Callable[[], datetime],
    delay_sec: float,
    rescue_threshold_min: float,
    buffer_minutes: float,
    process: ProcessCallback,
    sleep: Callable[[float], None] = time.sleep,
    initial_start_utc: datetime | None = None,
) -> None:
    """실시간 로그 라인 스트림을 소비하며 매치 종료마다 process 를 호출한다.

    `lines` 로 실제 `tail_follow()` (끝나지 않는 제너레이터) 를 넘기면 계속 돈다.
    `initial_start_utc` 는 부팅 시점에 이미 진행 중이던 매치의 시작 시각이다 —
    `discover_backlog()` 결과의 마지막 항목이 end_utc=None 이면 그게 이거다.
    (앱이 매치 도중에 시작돼 그 MATCH_START 줄을 못 본 경우를 위함. 앱이 매치
    종료 후에 재시작되면 그 매치는 이미 run_once() 의 백로그 복구가 처리한다.)
    """
    last_start_utc = initial_start_utc

    for line in lines:
        event = parse_line(line)
        if event is None:
            continue

        if event.type is LogEventType.MATCH_START:
            last_start_utc = event.local_time.replace(tzinfo=local_tz).astimezone(timezone.utc)
            continue

        # MATCH_END
        if last_start_utc is None:
            continue  # 시작을 모르는 매치 — extract_matches() 와 동일하게 무시

        end_utc = event.local_time.replace(tzinfo=local_tz).astimezone(timezone.utc)
        sleep(delay_sec)  # 마지막 세그먼트가 .tmp 에서 확정되길 대기 (SPEC §7.2)

        session_dir = find_session_for_time(recording_root, last_start_utc)
        if session_dir is not None:
            margin = remaining_margin_minutes(last_start_utc, now(), buffer_minutes)
            process(
                session_dir,
                MatchBoundary(start_utc=last_start_utc, end_utc=end_utc),
                should_rescue(margin, rescue_threshold_min),
            )

        last_start_utc = None
