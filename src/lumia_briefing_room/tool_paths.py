"""`tools/` 의 기본 경로를 한 곳에서 정한다 - 앱 설정(config.json)을 읽어 앱과 같은 위치를 쓴다.

도구마다 `~/Videos/LumiaBriefingRoom/clips` 를 박아 두었다가 저장 구조 변경(F7·F8: 풀영상 `full_video/steam_replay`,
클립 정보 앱 데이터 `library`)을 놓쳐, 클립 정보가 하나도 없는 폴더를 보고 조용히 반만 처리했다(2026-10-02).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from pathlib import Path

from lumia_briefing_room.config import ResolvedPaths, load_config, resolve_paths
from lumia_briefing_room.pipeline.clip_files import link_all


def app_paths(config_path: Path | None = None) -> ResolvedPaths:
    return resolve_paths(load_config(config_path).paths)


def clip_meta_files(meta_dir: Path) -> list[Path]:
    """클립 정보 파일(json) 목록. 하나도 없으면 경로가 틀렸을 가능성이 커서 경고한다."""
    files = sorted(meta_dir.glob("*.json")) if meta_dir.is_dir() else []
    if not files:
        print(f"⚠ 클립 정보(json)가 하나도 없다: {meta_dir} - 경로가 맞는지 확인할 것", file=sys.stderr)
    return files


def clip_videos(meta_dir: Path, clip_ids: Iterable[str], video_roots: Iterable[Path]) -> dict[str, Path]:
    """클립 ID → 영상 경로. 앱과 같은 방식(정보 파일 옆, 클립 영상 자리 아래 하위 폴더까지)으로 찾고, 못 찾은 ID 는 빠진다."""
    metas = []
    for clip_id in dict.fromkeys(clip_ids):
        try:
            meta = json.loads((meta_dir / f"{clip_id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(meta, dict):
            metas.append((clip_id, meta))
    if not metas:
        return {}
    primary = link_all([(meta_dir, metas)], tuple(video_roots)).primary
    return {clip_id: primary[(meta_dir, clip_id)] for clip_id, _ in metas if (meta_dir, clip_id) in primary}
