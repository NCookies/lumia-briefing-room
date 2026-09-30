"""태그 없는 옛 클립 영상의 내용 지문을 클립 정보에 기록해 둔다. (plan-fullvideo.md §3.10a-(5))

옛 클립 mp4 는 다시 쓰지 않으므로(클립당 수 초의 디스크 쓰기) `clipUid` 태그가 없다. 이전 직후에는 파일 이름으로 이어지지만, 그 뒤 탐색기에서
이름을 바꾸거나 옮기면 끊긴다. 그래서 (크기, 앞·뒤 1MiB 해시)를 `videoSizeBytes`·`videoFingerprint` 로 남겨 두면 그 뒤에도 내용으로 이어진다.
읽기(수 MB)는 락 밖에서, 기록만 짧게 락 안에서 하도록 "할 일 찾기"와 "기록"을 나눴다.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from lumia_briefing_room.pipeline.clip_files import content_fingerprint, find_video_for
from lumia_briefing_room.pipeline.clip_uid import write_json_atomic
from lumia_briefing_room.pipeline.mp4_tags import read_clip_uid


def pending_fingerprints(meta_dir: Path, roots: Iterable[Path]) -> list[tuple[Path, Path]]:
    """(정보 파일, 영상) - 지문이 없고 영상에 태그도 없는 클립."""
    roots = tuple(roots)
    pending: list[tuple[Path, Path]] = []
    if not meta_dir.is_dir():
        return pending
    for meta_path in sorted(meta_dir.glob("*.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict) or meta.get("videoFingerprint"):
            continue
        video = find_video_for(meta_path, roots)
        if video is not None and video.is_file() and read_clip_uid(video) is None:
            pending.append((meta_path, video))
    return pending


def store_fingerprint(meta_path: Path, video: Path) -> bool:
    """영상의 지문을 계산해 정보에 넣는다(읽어 고치는 사이 다른 요청이 고친 값은 덮지 않게 다시 읽는다). 이미 있거나 실패하면 False."""
    try:
        fingerprint, size = content_fingerprint(video), video.stat().st_size
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(meta, dict) or meta.get("videoFingerprint"):
        return False
    meta.update(videoFingerprint=fingerprint, videoSizeBytes=size)
    write_json_atomic(meta_path, meta)
    return True
