"""앱을 켤 때 옛 클립 폴더의 정보 파일을 앱 데이터 library 로 옮긴다. (plan-fullvideo.md §3.10a)"""

from __future__ import annotations

import logging

from pathlib import Path

from lumia_briefing_room.config import Config, resolve_paths, save_config, suggested_root, uses_legacy_layout
from lumia_briefing_room.pipeline.library_migrate import MigrationConflict, migrate_library
from lumia_briefing_room.pipeline.notices import NoticeCenter, notices

log = logging.getLogger(__name__)

MIGRATION_FAILED = "library_migration_failed"


def adopt_default_root(cfg: Config, config_path: Path | None) -> Config:
    """새로 설치한 사용자(옛 경로 설정도 옛 기본 폴더도 없음)는 기본 저장 폴더 구조로 시작한다. 이미 쓰던 사용자는 그대로 둔다."""
    root = suggested_root(cfg.paths)
    if root is None:
        return cfg
    cfg.paths.root = root
    if config_path is not None:
        save_config(cfg, config_path)
    return cfg


def migrate_legacy_layout(cfg: Config, center: NoticeCenter = notices) -> int:
    """옮긴 파일 수. 새 구조(`paths.root`)는 옮길 것이 없다. 옮기지 못해도 앱은 켜져야 하므로 예외 대신 알림을 올린다."""
    if not uses_legacy_layout(cfg.paths):
        return 0
    resolved = resolve_paths(cfg.paths)
    total = 0
    for old, library in ((resolved.clips_steam, resolved.library_steam), (resolved.clips_vod, resolved.library_vod)):
        try:
            total += migrate_library(old, library)
        except MigrationConflict as exc:
            log.error("클립 정보 이전을 중단했다(같은 이름에 다른 내용): %s", exc)
            center.post(
                MIGRATION_FAILED,
                "이전 버전의 클립 정보를 새 위치로 옮기지 못해 일부 클립이 목록에 보이지 않을 수 있습니다. 진단 정보를 보내 주세요.",
                title="클립 정보를 옮기지 못했습니다",
            )
        except OSError:
            log.exception("클립 정보 이전 중 오류: %s", old)
            center.post(
                MIGRATION_FAILED,
                "이전 버전의 클립 정보를 새 위치로 옮기는 중 오류가 났습니다. 앱을 다시 켜면 이어서 옮깁니다.",
                title="클립 정보를 옮기지 못했습니다",
            )
    if total:
        log.info("클립 정보 %d개를 앱 데이터 library 로 옮겼다", total)
    return total
