"""저장 위치를 바꾼다: 옛 경로(clips·vodClips·games)에서 저장 폴더 하나 구조로, 또는 저장 폴더를 다른 곳으로. (plan-fullvideo.md §3.10a-(3))

영상(클립 영상·풀영상 폴더·재생용 변환 영상)만 옮긴다. 클립 정보는 앱 데이터 library 에 있어 따라 옮기지 않는다.
파일 하나를 옮길 때마다 기록(ledger)에 남겨 두 번 돌려도 같고 중간에 꺼져도 이어 하며, `undo_storage_move` 가 되돌린다.
목적지에 같은 이름이 있거나 새 폴더가 옛 폴더 안쪽이면 아무것도 옮기기 전에 거부한다.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lumia_briefing_room.config import PathsConfig, ResolvedPaths
from lumia_briefing_room.pipeline.clip_files import move_file, walk_videos
from lumia_briefing_room.pipeline.game_files import valid_key
from lumia_briefing_room.pipeline.game_store import GAME_JSON


class StorageMoveError(Exception):
    """옮길 수 없는 이유를 사용자에게 그대로 보여 줄 수 있는 문장으로 담는다."""


@dataclass
class StoragePlan:
    pairs: list[tuple[Path, Path]]
    total_bytes: int
    old_bases: list[Path]  # 다 옮긴 뒤 비었으면 치울 옛 폴더
    dirs: list[tuple[Path, Path]]  # 영상 자리의 하위 폴더(사용자가 만든 빈 폴더 포함) 옛 → 새


def previous_paths(paths: PathsConfig) -> dict:
    """되돌릴 때 설정에 다시 넣을 값(설정 파일 키 이름)."""
    def text(p: Path | None) -> str | None:
        return None if p is None else str(p)

    return {
        "clips": text(paths.clips), "vodClips": text(paths.vod_clips), "games": text(paths.games),
        "root": text(paths.root), "fullVideos": text(paths.full_videos),
    }


def _is_inside(child: Path, parent: Path) -> bool:
    child, parent = child.resolve(), parent.resolve()
    return child != parent and parent in child.parents


def _video_bases(old: ResolvedPaths, new: ResolvedPaths) -> list[tuple[Path, Path]]:
    if len(old.clip_roots) == 1:
        return [(old.clip_roots[0], new.clip_roots[0])]
    return [(old.clips_steam, new.clips_steam), (old.clips_vod, new.clips_vod)]


def _subdirs(base: Path) -> list[Path]:
    found: list[Path] = []
    for current, names, _ in os.walk(base):
        names[:] = sorted(n for n in names if not n.startswith("."))
        found.extend(Path(current) / n for n in names)
    return found


def plan_storage_move(old: ResolvedPaths, new: ResolvedPaths) -> StoragePlan:
    pairs: list[tuple[Path, Path]] = []
    old_bases: list[Path] = []
    dirs: list[tuple[Path, Path]] = []

    def add_tree(src_base: Path, dst_base: Path, files, *, with_dirs: bool = False) -> None:
        if src_base.resolve() == dst_base.resolve():
            return
        if _is_inside(dst_base, src_base):
            raise StorageMoveError("새 폴더는 기존 폴더의 안쪽일 수 없습니다")
        old_bases.append(src_base)
        if with_dirs:
            dirs.extend((d, dst_base / d.relative_to(src_base)) for d in _subdirs(src_base))
        pairs.extend((f, dst_base / f.relative_to(src_base)) for f in files)

    for src_base, dst_base in _video_bases(old, new):
        add_tree(src_base, dst_base, walk_videos([src_base]), with_dirs=True)

    if old.proxy_cache.resolve() != new.proxy_cache.resolve() and old.proxy_cache.is_dir():
        add_tree(old.proxy_cache, new.proxy_cache, sorted(p for p in old.proxy_cache.glob("*.mp4") if p.is_file()))

    for games_dir in old.games_dirs:
        try:
            folders = sorted(p for p in games_dir.iterdir() if p.is_dir() and valid_key(p.name))
        except OSError:
            continue
        for folder in folders:
            target_base = new.games_vod if folder.name.startswith("vod_") else new.games_steam
            if folder.resolve() == (target_base / folder.name).resolve():
                continue
            if _is_inside(target_base / folder.name, folder):
                raise StorageMoveError("새 폴더는 기존 폴더의 안쪽일 수 없습니다")
            files = sorted((p for p in folder.rglob("*") if p.is_file()), key=lambda p: (p.name == GAME_JSON, str(p)))
            old_bases.append(folder)
            pairs.extend((f, target_base / folder.name / f.relative_to(folder)) for f in files)

    clashes = [dst for _, dst in pairs if dst.exists()]
    if clashes:
        raise StorageMoveError(f"새 위치에 같은 이름의 파일이 이미 있습니다: {', '.join(p.name for p in clashes[:3])}")
    if not pairs and not dirs:
        return StoragePlan(pairs=[], total_bytes=0, old_bases=[], dirs=[])
    old_bases.extend(old.games_dirs)
    if len(old.clip_roots) == 1:
        if old.games_steam.parent.name == "풀영상":
            old_bases.append(old.games_steam.parent)
        if old.proxy_cache.parent.name == ".cache":
            old_bases.append(old.proxy_cache.parent)
    old_bases.extend([old.staging_clips, old.staging_games])
    return StoragePlan(
        pairs=pairs, total_bytes=sum(src.stat().st_size for src, _ in pairs), old_bases=old_bases, dirs=dirs
    )


def _append(ledger: Path, entry: dict) -> None:
    with ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _remove_empty_dirs(base: Path, *, keep_base: bool) -> None:
    if not base.is_dir():
        return
    for child in sorted((p for p in base.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            child.rmdir()
        except OSError:
            pass
    if not keep_base:
        try:
            base.rmdir()
        except OSError:
            pass


def execute_storage_move(
    plan: StoragePlan, ledger: Path, *, previous: dict, progress: Callable[[int, int], None] | None = None
) -> int:
    """옮긴 파일 수. `previous` 는 되돌릴 때 돌려받을 옛 설정 값(처음 돌릴 때만 기록에 남긴다)."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    if not ledger.exists():
        _append(ledger, {"previous": previous})
    done = 0
    if progress is not None:
        progress(0, plan.total_bytes)
    for src_dir, dst_dir in plan.dirs:
        if not dst_dir.is_dir():
            dst_dir.mkdir(parents=True, exist_ok=True)
            _append(ledger, {"dirsrc": str(src_dir), "dirdst": str(dst_dir)})
    for src, dst in plan.pairs:
        size = src.stat().st_size
        move_file(src, dst, overwrite=False)
        _append(ledger, {"src": str(src), "dst": str(dst)})
        done += size
        if progress is not None:
            progress(done, plan.total_bytes)
    for base in plan.old_bases:
        _remove_empty_dirs(base, keep_base=False)
    return len(plan.pairs)


def undo_storage_move(ledger: Path) -> dict | None:
    """기록을 거꾸로 돌려 원래 자리로 되돌리고 옛 설정 값을 돌려준다. 원래 자리에 다른 파일이 생겼으면 아무것도 옮기지 않고 거부한다."""
    if not ledger.is_file():
        return None
    lines = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    previous = next((e["previous"] for e in lines if "previous" in e), None)
    todo = [(Path(e["dst"]), Path(e["src"])) for e in reversed(lines) if "src" in e and Path(e["dst"]).is_file()]
    blocked = [src for _, src in todo if src.exists()]
    if blocked:
        raise StorageMoveError(f"원래 자리에 같은 이름의 파일이 생겼습니다: {', '.join(p.name for p in blocked[:3])}")
    for dst, src in todo:
        move_file(dst, src, overwrite=False)
    for entry in reversed(lines):
        if "dirsrc" in entry:
            Path(entry["dirsrc"]).mkdir(parents=True, exist_ok=True)
            _remove_empty_dirs(Path(entry["dirdst"]), keep_base=False)
    ledger.unlink()
    return previous
