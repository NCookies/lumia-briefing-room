"""저장 공간을 재서 부족하면 알림을 올리고, 충분해지면 알림을 거둔다. (plan-fullvideo.md §3.4)"""

from __future__ import annotations

import logging

from lumia_briefing_room.config import Config, resolve_paths
from lumia_briefing_room.pipeline.disk_space import DiskStatus, check_disk
from lumia_briefing_room.pipeline.notices import NoticeCenter, notices

log = logging.getLogger(__name__)

DISK_LOW = "disk_low"
FULL_VIDEO_FAILED = "full_video_failed"


def disk_status(cfg: Config) -> DiskStatus:
    return check_disk(resolve_paths(cfg.paths).games, min_free_gb=cfg.paths.min_free_gb)


def check_and_notify(cfg: Config, center: NoticeCenter = notices) -> DiskStatus | None:
    """게임 처리 전과 앱 시작 때 부른다. 잴 수 없으면(드라이브 분리 등) 조용히 넘어간다."""
    try:
        status = disk_status(cfg)
    except OSError:
        log.warning("저장 공간을 확인하지 못했다", exc_info=True)
        return None
    if status.low:
        center.post(DISK_LOW, status.message, title="저장 공간이 부족합니다")
    else:
        center.clear(DISK_LOW)
    return status


def report_full_video_failure(message: str, center: NoticeCenter = notices) -> None:
    center.post(FULL_VIDEO_FAILED, message, title="풀영상을 저장하지 못했습니다")
