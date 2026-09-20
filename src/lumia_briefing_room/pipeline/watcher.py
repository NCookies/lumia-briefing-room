"""실시간 Player.log 감시 + 백로그 복구의 순수 로직. (SPEC §7.2, §7.2.1)

이 모듈은 "판단"만 한다 — 실제로 무한 루프를 돌며 tail_follow() 를 소비하고
process_match() 를 호출하는 배선(`run_forever` 류)은 아직 없다.
plan-pipeline.md §0 체크리스트의 다음 항목이다.
"""

import json
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path

from lumia_briefing_room.pipeline.playerlog import MatchBoundary, extract_matches
from lumia_briefing_room.video.session import RecordingSession, SessionParseError


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
