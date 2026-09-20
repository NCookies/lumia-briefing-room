from datetime import datetime, timedelta, timezone

import pytest

from lumia_briefing_room.cli.watch import build_parser, default_player_log_dir, make_processor
from lumia_briefing_room.config import Config, PathsConfig, discover_ffmpeg
from lumia_briefing_room.pipeline.playerlog import MatchBoundary
from lumia_briefing_room.video.session import RecordingSession

FFMPEG_PATH = discover_ffmpeg()
requires_ffmpeg = pytest.mark.skipif(FFMPEG_PATH is None, reason="ffmpeg 를 찾을 수 없다")


def test_build_parser_defaults():
    args = build_parser().parse_args([])
    assert args.game_mode == "battle_royale"
    assert args.recording_root is None


def test_default_player_log_dir_points_to_eternal_return():
    path = default_player_log_dir()
    assert path.parts[-2:] == ("NimbleNeuron", "Eternal Return")


@requires_ffmpeg
def test_make_processor_runs_without_rescue(tmp_path, make_synthetic_session):
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=5,
        start_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    cfg = Config(paths=PathsConfig(temp=tmp_path / "work", clips=tmp_path / "clips"))
    process = make_processor(
        cfg, FFMPEG_PATH, game_mode="battle_royale",
        k_templates=None, a_templates=None, hwaccel=None,
    )
    match = MatchBoundary(
        start_utc=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        end_utc=datetime(2026, 1, 1, 0, 0, 4, tzinfo=timezone.utc),
    )

    process(session_dir, match, False)  # 예외 없이 끝나면 통과 (탐지=0 이라 클립 없음)


@requires_ffmpeg
def test_make_processor_rescues_before_processing(tmp_path, make_synthetic_session):
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=5,
        start_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    work_dir = tmp_path / "work"
    cfg = Config(paths=PathsConfig(temp=work_dir, clips=tmp_path / "clips"))
    process = make_processor(
        cfg, FFMPEG_PATH, game_mode="battle_royale",
        k_templates=None, a_templates=None, hwaccel=None,
    )
    match = MatchBoundary(
        start_utc=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        end_utc=datetime(2026, 1, 1, 0, 0, 4, tzinfo=timezone.utc),
    )

    process(session_dir, match, True)

    rescued = work_dir / session_dir.name
    assert rescued.exists()
    assert (rescued / "session.mpd").exists()
