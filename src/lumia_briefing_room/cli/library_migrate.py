"""옛 클립 폴더의 앱 전용 정보 파일(json·썸네일·라벨·게임 기록·영상 색인)을 앱 데이터 library 폴더로 옮긴다. (docs/plan-fullvideo.md §3.10a)

usage:
    python -m lumia_briefing_room.cli.library_migrate [--config PATH] [--dry-run] [--undo]
        [--old PATH --lib PATH]

기본은 설정의 옛 경로 두 곳(스팀 클립·영상 파일 클립)을 각각 library\\steam·library\\vod 로 옮긴다. `--old`/`--lib` 로 한 쌍만 지정할 수 있다.
영상(mp4)은 옮기지 않는다. 두 번 돌려도 같은 결과이고, `--undo` 는 기록을 거꾸로 돌려 원래 자리로 되돌린다.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from lumia_briefing_room.config import load_config, resolve_paths
from lumia_briefing_room.pipeline.library_migrate import (
    MigrationBlocked,
    MigrationConflict,
    migrate_library,
    pending_files,
    undo_migration,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--old", type=Path, default=None)
    parser.add_argument("--lib", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="옮길 파일 수만 센다")
    parser.add_argument("--undo", action="store_true", help="기록을 거꾸로 돌려 원래 자리로 되돌린다")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if (args.old is None) != (args.lib is None):
        raise SystemExit("--old 와 --lib 는 같이 지정한다")
    if args.old is not None:
        pairs = [(args.old, args.lib)]
    else:
        resolved = resolve_paths(load_config(args.config).paths)
        pairs = [(resolved.clips_steam, resolved.library_steam), (resolved.clips_vod, resolved.library_vod)]
    for old, lib in pairs:
        try:
            if args.undo:
                print(f"{lib} -> {old}: {undo_migration(lib)}개 되돌림")
            elif args.dry_run:
                print(f"{old} -> {lib}: {len(pending_files(old, lib))}개 옮길 예정")
            else:
                print(f"{old} -> {lib}: {migrate_library(old, lib)}개 옮김")
        except MigrationConflict as e:
            raise SystemExit(f"같은 이름에 내용이 다른 파일이 있어 아무것도 옮기지 않았다: {e}")
        except MigrationBlocked as e:
            raise SystemExit(f"옛 휴지통에 클립이 남아 있다. 앱을 켜서 먼저 처리한다: {e}")


if __name__ == "__main__":
    main()
