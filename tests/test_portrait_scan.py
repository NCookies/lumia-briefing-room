from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from lumia_briefing_room.pipeline import portrait_scan
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.segments import SegmentRange
from lumia_briefing_room.video.session import RecordingSession

PROFILE = ResolutionProfile.for_resolution(2560, 1440)
VIVID = (250, 60, 40)


def _paint(frame: np.ndarray, roi_name: str, color: tuple[int, int, int]) -> None:
    roi = PROFILE.rois[roi_name]
    frame[roi.y0 : roi.y1, roi.x0 : roi.x1] = color


def _route_select_frame() -> np.ndarray:
    frame = np.full((1440, 2560, 3), 20, dtype=np.uint8)
    for base in ("portrait", "teammate1", "teammate2"):
        _paint(frame, base, VIVID)
        _paint(frame, f"{base}_display", VIVID)
    return frame


def _blank_frame() -> np.ndarray:
    return np.full((1440, 2560, 3), 20, dtype=np.uint8)


def _fake_session(tmp_path: Path) -> RecordingSession:
    """`existing_segment_numbers` 가 실제로 훑을 세션 - 세그먼트 파일 존재 여부만 있으면 되므로
    빈 파일로 흉내 낸다(디코딩은 `extract_keyframe_frames` 를 몽키패치해 건너뛴다)."""
    session_dir = tmp_path / "bg_999999_20260101_000000"
    session_dir.mkdir()
    (session_dir / "init-stream0.m4s").write_bytes(b"")
    for n in range(0, 40):
        (session_dir / f"chunk-stream0-{n:05d}.m4s").write_bytes(b"")
    return RecordingSession(
        directory=session_dir,
        app_id=999999,
        start_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        width=2560,
        height=1440,
        segment_duration_sec=3.0,
        buffer_minutes=None,
    )


def test_find_match_portraits_tries_backward_before_forward_and_uses_the_closest_hit(
    tmp_path, monkeypatch
):
    """실측(2026-09-29): `matchStartUtc` 이전에 루트 선택 화면이 떠 있던 경기가 있었다 -
    뒤(순방향)를 보기 전에 앞(역방향, 가까운 순)을 먼저 봐야 한다."""
    session = _fake_session(tmp_path)
    seg_range = SegmentRange(first=20, last=25)
    calls: list[list[int]] = []

    def fake_extract(sess, *, stream, segment_numbers, ffmpeg_path, hwaccel=None):
        calls.append(list(segment_numbers))
        for n in segment_numbers:
            # seg_range.first - 1(=19)에 딱 붙은 프레임만 초상화가 보인다.
            yield (float(n), _route_select_frame() if n == 19 else _blank_frame())

    monkeypatch.setattr(portrait_scan, "extract_keyframe_frames", fake_extract)

    found = portrait_scan.find_match_portraits(session, seg_range, ffmpeg_path=Path("ffmpeg"))

    assert found is not None
    assert len(calls) == 1, "역방향에서 찾았으면 순방향(뒤쪽) 호출은 필요 없다"
    assert calls[0][-1] == 19, "역방향 훑기는 matchStartUtc 에 가장 가까운(직전) 세그먼트로 끝나야 한다"
    assert calls[0] == sorted(calls[0]), "세그먼트 추출 자체는 항상 오름차순으로 요청한다(디코딩 순서)"


def test_find_match_portraits_falls_back_to_forward_scan_when_backward_finds_nothing(
    tmp_path, monkeypatch
):
    session = _fake_session(tmp_path)
    seg_range = SegmentRange(first=20, last=25)
    calls: list[list[int]] = []

    def fake_extract(sess, *, stream, segment_numbers, ffmpeg_path, hwaccel=None):
        calls.append(list(segment_numbers))
        for n in segment_numbers:
            yield (float(n), _route_select_frame() if n == 22 else _blank_frame())

    monkeypatch.setattr(portrait_scan, "extract_keyframe_frames", fake_extract)

    found = portrait_scan.find_match_portraits(session, seg_range, ffmpeg_path=Path("ffmpeg"))

    assert found is not None
    assert len(calls) == 2, "역방향에서 못 찾았으면 순방향(뒤쪽)도 봐야 한다"
    assert calls[1][0] == seg_range.first


def test_find_match_portraits_returns_none_when_neither_direction_has_it(tmp_path, monkeypatch):
    session = _fake_session(tmp_path)
    seg_range = SegmentRange(first=20, last=25)

    def fake_extract(sess, *, stream, segment_numbers, ffmpeg_path, hwaccel=None):
        for n in segment_numbers:
            yield (float(n), _blank_frame())

    monkeypatch.setattr(portrait_scan, "extract_keyframe_frames", fake_extract)

    assert portrait_scan.find_match_portraits(session, seg_range, ffmpeg_path=Path("ffmpeg")) is None
