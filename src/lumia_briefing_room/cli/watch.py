"""Player.log 를 실시간으로 감시하며 매치가 끝날 때마다 자동으로 클립을 뽑는다.

SPEC §3/§7.2 의 실제 배선: 부팅 시 백로그 복구(run_once) -> 실시간 감시(run_forever).
Ctrl+C 로 멈출 때까지 끝나지 않는다.

usage:
    python -m lumia_briefing_room.cli.watch --recording-root "H:\\steam video\\video"
        [--config PATH] [--ffmpeg PATH] [--game-mode battle_royale|cobalt]
        [--k-templates PATH] [--a-templates PATH] [--hwaccel NAME] [--player-log-dir PATH]
"""

import argparse
import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from lumia_briefing_room.config import (
    FFMPEG_NOT_FOUND_MESSAGE,
    Config,
    discover_ffmpeg,
    load_config,
    resolve_paths,
)
from lumia_briefing_room.detect.counter import load_templates
from lumia_briefing_room.pipeline.clip import ClipCutError
from lumia_briefing_room.pipeline.orchestrator import process_match
from lumia_briefing_room.pipeline.playerlog import MatchBoundary, tail_follow
from lumia_briefing_room.pipeline.watcher import (
    ProcessCallback,
    ProcessedState,
    discover_backlog,
    resolve_buffer_minutes,
    rescue_copy,
    run_forever,
    run_once,
)
from lumia_briefing_room.steam_paths import discover_recording_root
from lumia_briefing_room.video.segments import segment_time_range
from lumia_briefing_room.video.session import RecordingSession

log = logging.getLogger("lumia_briefing_room.watch")


def default_player_log_dir() -> Path:
    local_low = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "AppData" / "LocalLow"
    return local_low / "NimbleNeuron" / "Eternal Return"


def make_processor(
    cfg: Config,
    ffmpeg_path: Path,
    *,
    game_mode: str,
    k_templates: dict | None,
    a_templates: dict | None,
    hwaccel: str | None,
) -> ProcessCallback:
    resolved = resolve_paths(cfg.paths)

    def _process(session_dir: Path, match: MatchBoundary, rescue: bool) -> None:
        session = RecordingSession.load(session_dir)

        if rescue:
            seg_range = segment_time_range(session, match.start_utc, match.end_utc)
            rescued_dir = rescue_copy(session, seg_range, resolved.temp)
            session = RecordingSession.load(rescued_dir)
            log.info("남은 여유가 적어 원본을 먼저 복사함: %s", rescued_dir)

        try:
            written = process_match(
                session, match.start_utc, match.end_utc, cfg,
                ffmpeg_path=ffmpeg_path, game_mode=game_mode,
                k_templates=k_templates, a_templates=a_templates, hwaccel=hwaccel,
            )
        except ClipCutError as exc:
            log.warning("클립 생성 실패(세그먼트 없음): %s", exc)
            return

        log.info("매치 %s: 클립 %d개", match.start_utc.isoformat(), len(written))

    return _process


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--ffmpeg", type=Path, default=None)
    parser.add_argument("--recording-root", type=Path, default=None)
    parser.add_argument("--player-log-dir", type=Path, default=None)
    parser.add_argument("--game-mode", default="battle_royale")
    parser.add_argument("--k-templates", type=Path, default=None)
    parser.add_argument("--a-templates", type=Path, default=None)
    parser.add_argument("--hwaccel", type=str, default=None)
    parser.add_argument("--once", action="store_true", help="백로그만 처리하고 종료한다")
    return parser


def run(
    args: argparse.Namespace,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    should_stop: Callable[[], bool] = lambda: False,
) -> None:
    cfg = load_config(args.config)
    ffmpeg_path = args.ffmpeg or discover_ffmpeg()
    if ffmpeg_path is None:
        raise SystemExit(FFMPEG_NOT_FOUND_MESSAGE)

    recording_root = args.recording_root or cfg.paths.steam_recording or discover_recording_root()
    if recording_root is None:
        raise SystemExit(
            "녹화 폴더를 찾을 수 없다 - 스팀 배경 녹화를 한 번도 설정한 적이 없거나 "
            "스팀이 이 계정으로 설치되어 있지 않은 것으로 보인다. "
            "--recording-root 또는 paths.steamRecording 설정으로 직접 지정할 것."
        )

    player_log_dir = args.player_log_dir or cfg.watch.player_log or default_player_log_dir()
    player_log = player_log_dir / "Player.log"
    player_prev_log = player_log_dir / "Player-prev.log"

    k_templates = load_templates(args.k_templates) if args.k_templates else None
    a_templates = load_templates(args.a_templates) if args.a_templates else None
    process = make_processor(
        cfg, ffmpeg_path, game_mode=args.game_mode,
        k_templates=k_templates, a_templates=a_templates, hwaccel=args.hwaccel,
    )

    local_tz = datetime.now().astimezone().tzinfo
    resolved = resolve_paths(cfg.paths)
    resolved.temp.mkdir(parents=True, exist_ok=True)
    state_path = resolved.temp / "processed_matches.json"
    buffer_minutes = resolve_buffer_minutes(cfg, recording_root)

    matches = discover_backlog(player_log, player_prev_log, local_tz=local_tz)
    log.info("백로그 매치 %d개 발견", len(matches))

    state = ProcessedState.load(state_path)
    run_once(
        matches, state,
        recording_root=recording_root, now=now,
        rescue_threshold_min=cfg.watch.rescue_threshold_min,
        buffer_minutes=buffer_minutes,
        process=process, state_path=state_path,
    )

    if args.once:
        log.info("백로그 처리 완료 - --once 라서 종료한다")
        return

    # 부팅 시점에 이미 진행 중이던 매치(끝나지 않은 채로 로그 끝에 남음)를
    # 실시간 감시가 이어서 잡을 수 있게 시드한다 (watcher.run_forever 문서 참고).
    initial_start = matches[-1].start_utc if matches and matches[-1].end_utc is None else None

    log.info("Player.log 감시 시작: %s", player_log)
    run_forever(
        tail_follow(
            player_log,
            poll_interval_sec=cfg.watch.poll_interval_ms / 1000,
            should_stop=should_stop,
        ),
        local_tz=local_tz, recording_root=recording_root, now=now,
        delay_sec=cfg.watch.delay_sec,
        rescue_threshold_min=cfg.watch.rescue_threshold_min,
        buffer_minutes=buffer_minutes,
        process=process, initial_start_utc=initial_start,
    )


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(build_parser().parse_args(argv))


if __name__ == "__main__":
    main()
