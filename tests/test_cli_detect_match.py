import json

import pytest

from lumia_briefing_room.cli.detect_match import build_parser, main, result_to_json
from lumia_briefing_room.config import discover_ffmpeg
from lumia_briefing_room.detect.types import CombatInterval, MatchDetection

FFMPEG_PATH = discover_ffmpeg()
requires_ffmpeg = pytest.mark.skipif(FFMPEG_PATH is None, reason="ffmpeg를 찾을 수 없다")


def test_result_to_json_shapes_output():
    result = MatchDetection(
        intervals=[
            CombatInterval(
                start=6.0, end=24.0, tags=frozenset({"kill", "assist"}),
                k_delta=1, a_delta=1, died=False, day_night="day", confidence=0.9,
            )
        ],
        k_final=1, a_final=1, gaps=[], source_incomplete=False,
    )

    payload = result_to_json(result)

    assert payload["kFinal"] == 1
    assert payload["sourceIncomplete"] is False
    assert payload["intervals"][0]["tags"] == ["assist", "kill"]
    assert payload["intervals"][0]["start"] == 6.0


def test_build_parser_parses_iso_datetimes():
    parser = build_parser()
    args = parser.parse_args(
        ["/tmp/session", "2026-09-19T13:07:47+00:00", "2026-09-19T13:08:00+00:00"]
    )
    assert args.match_start.isoformat() == "2026-09-19T13:07:47+00:00"
    assert args.stream == 0


@requires_ffmpeg
def test_main_prints_json_for_synthetic_session(tmp_path, make_synthetic_session, capsys):
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=5
    )

    main(
        [
            str(session_dir),
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:05+00:00",
            "--ffmpeg",
            str(FFMPEG_PATH),
        ]
    )

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "kFinal" in payload
    assert "intervals" in payload
