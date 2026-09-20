import pytest

from lumia_briefing_room.cli.process_match import build_parser, main
from lumia_briefing_room.config import discover_ffmpeg

FFMPEG_PATH = discover_ffmpeg()
requires_ffmpeg = pytest.mark.skipif(FFMPEG_PATH is None, reason="ffmpeg를 찾을 수 없다")


def test_build_parser_defaults():
    parser = build_parser()
    args = parser.parse_args(
        ["/tmp/session", "2026-09-19T13:07:47+00:00", "2026-09-19T13:08:00+00:00"]
    )
    assert args.game_mode == "battle_royale"
    assert args.config is None


@requires_ffmpeg
def test_main_reports_no_clips_when_nothing_detected(tmp_path, make_synthetic_session, capsys):
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=5
    )
    clips_dir = tmp_path / "clips"

    main(
        [
            str(session_dir),
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:05+00:00",
            "--ffmpeg", str(FFMPEG_PATH),
            "--clips-dir", str(clips_dir),
        ]
    )

    out = capsys.readouterr().out
    assert "클립 없음" in out
