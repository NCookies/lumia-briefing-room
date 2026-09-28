"""경기 시작 직후 루트 선택 화면에서 초상화 3장을 찾는다(SPEC §2.10·§2.12, plan-ui.md §0).

`pipeline/result_scan.py` 가 경기 끝을 훑는 것과 대칭으로, 경기 시작 쪽을 짧게(`PORTRAIT_SCAN_SEC`)
훑는다. OCR 이 필요 없어(픽셀 판정뿐) 결과 화면 찾기보다 훨씬 싸다.

실측(2026-09-29, 실제 녹화 2경기): 캐릭터 선택→루트 선택→로딩→팀 로비로 이어지는 진행 속도가
경기마다 다르다 - 한 경기는 `matchStartUtc` 시점에 이미 루트 선택 화면이었고, 다른 경기는
같은 시점에 아직 캐릭터 선택 화면이었다가 8초 만에 팀 로비까지 넘어갔다(플레이어가 저장된
빌드를 빠르게 확정한 경우로 보인다). `PORTRAIT_SCAN_SEC` 를 넉넉히 잡아 두되, 아주 빠르게
넘어가는 경기는 그래도 놓칠 수 있다 - `detect/portrait.py::find_portraits_in_frames` 가 그런
경우 예외 없이 그냥 None 을 돌려주므로 클립 생성 자체는 막지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image

from lumia_briefing_room.detect.portrait import find_portraits_in_frames
from lumia_briefing_room.detect.types import PortraitCrops
from lumia_briefing_room.pipeline.vod_games import GameSpan
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.frames import extract_keyframe_frames
from lumia_briefing_room.video.segments import SegmentRange, existing_segment_numbers
from lumia_briefing_room.video.session import RecordingSession
from lumia_briefing_room.video.vod import VodFileSource, find_ffprobe

PORTRAIT_SCAN_SEC = 120.0
PORTRAIT_SLOTS = ("me", "teammate1", "teammate2")


def portrait_image_name(match_start: datetime, slot: str) -> str:
    return f"{match_start:%Y%m%d_%H%M%S}_portrait_{slot}.jpg"


def save_portrait_image(image, path: Path) -> None:
    """초상화 크롭은 이미 작아서(수백 px) 결과표 이미지처럼 리사이즈하지 않고 그대로 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image).save(path, quality=90)


def find_match_portraits(
    session: RecordingSession,
    seg_range: SegmentRange,
    *,
    ffmpeg_path: Path,
    profile: ResolutionProfile | None = None,
    hwaccel: str | None = None,
) -> PortraitCrops | None:
    """스팀 녹화: 경기 시작 세그먼트부터 짧게 훑어 초상화를 찾는다."""
    profile = profile or ResolutionProfile.for_resolution(session.width, session.height)
    scan_segments = max(1, round(PORTRAIT_SCAN_SEC / session.segment_duration_sec))
    last = min(seg_range.last, seg_range.first + scan_segments - 1)
    numbers = existing_segment_numbers(session, 0, seg_range.first, last)
    frames = extract_keyframe_frames(
        session, stream=0, segment_numbers=numbers, ffmpeg_path=ffmpeg_path, hwaccel=hwaccel
    )
    return find_portraits_in_frames(frames, profile)


def find_vod_portraits(
    video_path: Path,
    span: GameSpan,
    *,
    ffmpeg_path: Path,
    profile: ResolutionProfile,
    hwaccel: str | None = None,
) -> PortraitCrops | None:
    """다시보기(VOD): 게임 구간 시작부터 짧게 훑어 초상화를 찾는다."""
    ffprobe_path = find_ffprobe(ffmpeg_path)
    end = min(span.end, span.start + PORTRAIT_SCAN_SEC)
    source = VodFileSource(
        video_path, ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path,
        start_sec=span.start, end_sec=end, hwaccel=hwaccel,
    )
    frames = source.frames()
    try:
        return find_portraits_in_frames(frames, profile)
    finally:
        frames.close()
