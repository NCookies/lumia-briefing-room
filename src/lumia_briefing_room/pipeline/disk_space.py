"""풀영상이 차지할 디스크 공간을 어림하고 부족 여부를 판정한다. (plan-fullvideo.md §3.4)"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MB_PER_MIN = 190.0  # 스팀 녹화 2560x1440 실측 (docs/spec/game.md §4)
DEFAULT_GAME_MINUTES = 15.0
RECENT_GAMES = 5
WARN_GAMES = 5  # 여유 공간이 게임 몇 개 몫보다 적으면 알린다
RECOMMENDED_GB = (50, 100)
GB = 2**30


@dataclass(frozen=True)
class DiskStatus:
    free_bytes: int
    expected_bytes: int
    threshold_bytes: int
    low: bool
    message: str | None


def expected_game_bytes(recent_sizes: list[int]) -> int:
    """예상 게임 용량: 최근 풀영상 크기의 평균. 기록이 없을 때만 분당 190MB × 15분."""
    recent = [s for s in recent_sizes if s > 0][-RECENT_GAMES:]
    if not recent:
        return int(DEFAULT_MB_PER_MIN * DEFAULT_GAME_MINUTES * 2**20)
    return sum(recent) // len(recent)


def evaluate(*, free_bytes: int, expected_bytes: int, min_free_gb: float) -> DiskStatus:
    threshold = max(expected_bytes * WARN_GAMES, int(min_free_gb * GB))
    low = free_bytes < threshold
    message = None
    if low:
        message = (
            f"여유 공간이 {free_bytes / GB:.1f}GB 남았습니다. 풀영상 자동 정리를 켜거나 한도를 확인하고, "
            "오래된 풀영상과 저장한 클립을 정리해 주세요."
        )
    return DiskStatus(free_bytes, expected_bytes, threshold, low, message)


def recent_full_video_sizes(games_dir: Path) -> list[int]:
    """`game.json` 에 기록된 풀영상 크기를 오래된 게임부터(경기 키 순) 돌려준다."""
    sizes: list[int] = []
    try:
        folders = sorted(p for p in games_dir.iterdir() if p.is_dir())
    except OSError:
        return sizes
    for folder in folders:
        try:
            data = json.loads((folder / "game.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        video = data.get("fullVideo") if isinstance(data, dict) else None
        size = video.get("sizeBytes") if isinstance(video, dict) else None
        if isinstance(size, int) and size > 0:
            sizes.append(size)
    return sizes


def free_bytes_at(folder: Path) -> int:
    probe = folder
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def check_disk(games_dir: Path, *, min_free_gb: float) -> DiskStatus:
    return evaluate(
        free_bytes=free_bytes_at(games_dir),
        expected_bytes=expected_game_bytes(recent_full_video_sizes(games_dir)),
        min_free_gb=min_free_gb,
    )
