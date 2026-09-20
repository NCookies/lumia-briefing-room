import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from label_combat import append_label, draft_label  # noqa: E402

from lumia_briefing_room.config import discover_ffmpeg
from lumia_briefing_room.video.session import RecordingSession

FFMPEG_PATH = discover_ffmpeg()
requires_ffmpeg = pytest.mark.skipif(FFMPEG_PATH is None, reason="ffmpeg를 찾을 수 없다")


@requires_ffmpeg
def test_draft_label_has_expected_shape(tmp_path, make_synthetic_session):
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    session_dir = make_synthetic_session(
        tmp_path, width=64, height=48, fps=10, segment_frames=10, num_segments=5,
        start_utc=start,
    )
    session = RecordingSession.load(session_dir)

    label = draft_label(
        session, start, start.replace(second=5), ffmpeg_path=FFMPEG_PATH
    )

    assert label["session_dir"] == str(session_dir)
    assert "combats" in label and isinstance(label["combats"], list)
    assert label["deaths"] == []
    assert "k_final" in label
    assert "a_final" in label


def test_append_label_writes_valid_jsonl(tmp_path):
    path = tmp_path / "labels.jsonl"
    append_label(path, {"a": 1})
    append_label(path, {"b": 2})

    lines = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"b": 2}
