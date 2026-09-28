"""경기 시작 직후 루트 선택 화면에서 초상화 3장을 찾는다(SPEC §2.10·§2.12, plan-ui.md §0).

`pipeline/result_scan.py` 가 경기 끝을 훑는 것과 대칭으로, 경기 시작 쪽을 짧게(`PORTRAIT_SCAN_SEC`)
훑는다. OCR 이 필요 없어(픽셀 판정뿐) 결과 화면 찾기보다 훨씬 싸다.

실측(2026-09-29, 실제 녹화 2경기): 캐릭터 선택→루트 선택→로딩→팀 로비로 이어지는 진행 속도가
경기마다 다르다 - 한 경기는 `matchStartUtc` 시점에 이미 루트 선택 화면이었고, 다른 경기는
같은 시점에 아직 캐릭터 선택 화면이었다가 8초 만에 팀 로비까지 넘어갔다(플레이어가 저장된
빌드를 빠르게 확정한 경우로 보인다). `PORTRAIT_SCAN_SEC` 를 넉넉히 잡아 두되, 아주 빠르게
넘어가는 경기는 그래도 놓칠 수 있다 - `detect/portrait.py::find_portraits_in_frames` 가 그런
경우 예외 없이 그냥 None 을 돌려주므로 클립 생성 자체는 막지 않는다.

**재실측(2026-09-29, 같은 날 후속)**: 위 "8초 만에 넘어갔다"던 경기를 프레임 단위로 다시
훑어 보니, 루트 선택 화면은 사실 사라진 게 아니라 **`matchStartUtc` 이전 최대 22초 구간에
멀쩡히 떠 있었다** - `matchStartUtc` 는 캐릭터·루트 선택이 다 끝난 뒤(로그 기준 "매치 시작")
를 가리킬 수 있어, 그 앞쪽을 전혀 안 본 게 진짜 원인이었다. 그래서 `matchStartUtc` 앞쪽을
`PORTRAIT_BACK_SCAN_SEC` 만큼 먼저 훑고(가까운 시점부터 거슬러 올라가며 찾는다 - 더 옛날로
갈수록 앞 경기의 로비·게임 화면일 위험이 커지므로), 못 찾으면 기존처럼 뒤쪽을 훑는다.
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
PORTRAIT_BACK_SCAN_SEC = 45.0
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
    """스팀 녹화: `matchStartUtc` 앞쪽(가까운 순)을 먼저, 못 찾으면 뒤쪽을 훑어 초상화를 찾는다."""
    profile = profile or ResolutionProfile.for_resolution(session.width, session.height)
    seg_sec = session.segment_duration_sec

    back_segments = max(1, round(PORTRAIT_BACK_SCAN_SEC / seg_sec))
    back_numbers = existing_segment_numbers(
        session, 0, max(0, seg_range.first - back_segments), seg_range.first - 1
    )
    if back_numbers:
        back_frames = list(extract_keyframe_frames(
            session, stream=0, segment_numbers=back_numbers, ffmpeg_path=ffmpeg_path, hwaccel=hwaccel
        ))
        found = find_portraits_in_frames(reversed(back_frames), profile)
        if found is not None:
            return found

    scan_segments = max(1, round(PORTRAIT_SCAN_SEC / seg_sec))
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
    """다시보기(VOD): 게임 구간 시작 앞쪽(가까운 순)을 먼저, 못 찾으면 뒤쪽을 훑어 초상화를 찾는다."""
    ffprobe_path = find_ffprobe(ffmpeg_path)

    back_start = max(0.0, span.start - PORTRAIT_BACK_SCAN_SEC)
    if back_start < span.start:
        back_source = VodFileSource(
            video_path, ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path,
            start_sec=back_start, end_sec=span.start, hwaccel=hwaccel,
        )
        back_frame_iter = back_source.frames()
        try:
            back_frames = list(back_frame_iter)
        finally:
            back_frame_iter.close()
        found = find_portraits_in_frames(reversed(back_frames), profile)
        if found is not None:
            return found

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
