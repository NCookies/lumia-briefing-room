"""저장 폴더 이름을 한글에서 영어로 바꾼다. (plan-fullvideo.md §3.10)

옛 새 구조(`클립\{스팀 녹화,영상 파일}`·`풀영상\{스팀 녹화,영상 파일}`)를 쓰던 사용자의 폴더를 앱을 켤 때 옮긴다:
`클립`→`clips`, `풀영상`→`full_video`, 그 안 `스팀 녹화`→`steam_replay`, `영상 파일`→`vod`.
클립은 스팀 녹화/영상 파일로 나누지 않으므로 `클립\스팀 녹화`·`클립\영상 파일` 의 내용은 `clips\자동 보관` 으로 옮긴다.
같은 이름이 이미 있으면 덮어쓰지 않고 합치며(파일은 ` (2)` 를 붙임), 폴더 하나가 실패해도 나머지는 계속한다.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from lumia_briefing_room.config import (
    AUTO_ARCHIVE_FOLDER,
    CLIPS_FOLDER,
    FULL_VIDEOS_FOLDER,
    STEAM_FOLDER,
    VOD_FOLDER,
    PathsConfig,
)

log = logging.getLogger(__name__)

OLD_CLIPS = "클립"
OLD_FULL_VIDEOS = "풀영상"
OLD_STEAM = "스팀 녹화"
OLD_VOD = "영상 파일"


def _unique(target: Path) -> Path:
    n = 2
    while True:
        candidate = target.with_name(f"{target.stem} ({n}){target.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def _merge(src: Path, dst: Path) -> int:
    """`src` 를 `dst` 로 옮긴다(있으면 합침). 옮긴 항목 수."""
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
        return 1
    moved = 0
    for child in sorted(src.iterdir()):
        target = dst / child.name
        if child.is_dir() and target.is_dir():
            moved += _merge(child, target)
        else:
            os.replace(child, _unique(target) if target.exists() else target)
            moved += 1
    try:
        src.rmdir()
    except OSError:
        pass
    return moved


def _attempt(src: Path, dst: Path) -> int:
    if not src.is_dir():
        return 0
    try:
        return _merge(src, dst)
    except OSError:
        log.exception("폴더 이름을 바꾸지 못했다: %s → %s", src, dst)
        return 0


def migrate_folder_names(cfg: PathsConfig) -> int:
    """옮긴 항목 수. 새 구조(`paths.root`)만 대상이다."""
    if cfg.root is None:
        return 0
    root = cfg.root
    moved = _attempt(root / OLD_CLIPS, root / CLIPS_FOLDER)
    clips = root / CLIPS_FOLDER
    for old in (OLD_STEAM, OLD_VOD):
        moved += _attempt(clips / old, clips / AUTO_ARCHIVE_FOLDER)
    if cfg.full_videos is None:
        moved += _attempt(root / OLD_FULL_VIDEOS, root / FULL_VIDEOS_FOLDER)
    full = cfg.full_videos or root / FULL_VIDEOS_FOLDER
    moved += _attempt(full / OLD_STEAM, full / STEAM_FOLDER)
    moved += _attempt(full / OLD_VOD, full / VOD_FOLDER)
    return moved
