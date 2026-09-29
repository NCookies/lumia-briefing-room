"""ffmpeg 자식 프로세스 실패를 사용자에게 보여줄 메시지로 바꾼다.

클립 컷·썸네일은 전부 ffmpeg 로 파일을 쓰는데(clip.py, vod_clips.py), 디스크 용량이
부족하면 `subprocess.CalledProcessError` 가 올라온다. 이걸 그냥 `str()` 하면
"Command '[...]' returned non-zero exit status 1." 처럼 종료 코드만 남고 ffmpeg 가
stderr 에 찍은 실제 원인("No space left on device")은 사라진다
(procs.py::run_hidden 이 capture_output=True 로 잡아 두지만 아무도 안 읽었다) -
그래서 stderr 를 직접 봐서 디스크 풀 여부를 판별하고, 사용자 친화적인 한국어
메시지로 바꾼다.
"""

from __future__ import annotations

import subprocess

_DISK_FULL_MARKERS = (
    "no space left on device",
    "not enough space",
    "disk full",
    "there is not enough space on the disk",
)

DISK_FULL_MESSAGE = (
    "저장 공간이 부족해 클립 추출이 중단됐습니다. 여유 공간을 확보한 뒤 이어서 진행해 주세요."
)


def _stderr_text(exc: BaseException) -> str:
    stderr = getattr(exc, "stderr", None)
    if stderr is None:
        return ""
    if isinstance(stderr, bytes):
        return stderr.decode("utf-8", errors="replace")
    return str(stderr)


def is_disk_full_error(exc: BaseException) -> bool:
    text = _stderr_text(exc).lower()
    return any(marker in text for marker in _DISK_FULL_MARKERS)


def describe_clip_error(exc: BaseException) -> str:
    """실패한 클립 작업의 예외를 화면에 보여줄 한 줄 메시지로 바꾼다."""
    if is_disk_full_error(exc):
        return DISK_FULL_MESSAGE
    if isinstance(exc, subprocess.CalledProcessError):
        detail = _stderr_text(exc).strip()
        return f"영상 처리가 실패했습니다: {detail}" if detail else f"영상 처리가 실패했습니다 ({exc})."
    return str(exc)
