"""옛 클립 폴더에 섞여 있던 앱 전용 정보 파일을 앱 데이터의 library 폴더로 옮긴다. (plan-fullvideo.md §3.10a)

영상(mp4)·`.proxy`·`.trash`(옛 휴지통 - 복원하면 정보 파일이 옛 자리로 돌아오니 그때 다시 돌린다)는 건드리지 않는다. 한 파일씩 임시 이름으로 복사 → 크기 확인 → `os.replace` →
원본 삭제 → 기록 순이라 중간에 꺼져도 깨지지 않고, 다시 돌리면 이어서 한다.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path

LEDGER_NAME = "migration.jsonl"
INFO_DIRS = (".thumbs", ".labels", ".games", ".vods")
TRASH_DIRNAME = ".trash"
STAGING_DIRNAME = ".staging"


class MigrationConflict(Exception):
    """목적지에 내용이 다른 같은 이름의 파일이 있다. 아무것도 옮기지 않는다."""


def _same_content(a: Path, b: Path) -> bool:
    if a.stat().st_size != b.stat().st_size:
        return False
    with a.open("rb") as fa, b.open("rb") as fb:
        while True:
            ca, cb = fa.read(1 << 20), fb.read(1 << 20)
            if ca != cb:
                return False
            if not ca:
                return True


def _pairs(old: Path, lib: Path) -> list[tuple[Path, Path]]:
    pairs = [(p, lib / p.name) for p in sorted(old.glob("*.json")) if p.is_file()]
    for name in INFO_DIRS:
        folder = old / name
        if folder.is_dir():
            pairs += [(p, lib / p.relative_to(old)) for p in sorted(folder.rglob("*")) if p.is_file()]
    return pairs


def pending_files(old: Path, lib: Path) -> list[tuple[Path, Path]]:
    """아직 옮기지 않은 (원본, 목적지) 쌍. 옛 폴더가 없으면 빈 목록."""
    return _pairs(old, lib) if old.is_dir() else []


def _move_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp")
    tmp.unlink(missing_ok=True)
    shutil.copyfile(src, tmp)
    if tmp.stat().st_size != src.stat().st_size:
        tmp.unlink(missing_ok=True)
        raise OSError(f"복사한 크기가 다르다: {src}")
    os.replace(tmp, dst)
    src.unlink()


def _append_ledger(lib: Path, src: Path, dst: Path) -> None:
    lib.mkdir(parents=True, exist_ok=True)
    with (lib / LEDGER_NAME).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"src": str(src), "dst": str(dst)}, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _remove_empty_tree(folder: Path) -> None:
    if folder.is_dir() and not any(p.is_file() for p in folder.rglob("*")):
        shutil.rmtree(folder, ignore_errors=True)


def migrate_library(old: Path, lib: Path, *, on_file: Callable[[Path, Path], None] | None = None) -> int:
    """옮긴 파일 수. 충돌이 하나라도 있으면 아무것도 옮기기 전에 `MigrationConflict`."""
    if not old.is_dir():
        return 0
    pairs = _pairs(old, lib)
    for src, dst in pairs:
        if dst.exists() and not _same_content(src, dst):
            raise MigrationConflict(str(dst))
    for tmp in list(lib.rglob("*.tmp")) if lib.is_dir() else []:
        tmp.unlink(missing_ok=True)
    moved = 0
    for src, dst in pairs:
        if on_file:
            on_file(src, dst)
        if dst.exists():
            src.unlink()
        else:
            _move_file(src, dst)
        _append_ledger(lib, src, dst)
        moved += 1
    for name in INFO_DIRS:
        _remove_empty_tree(old / name)
    _remove_empty_tree(old / STAGING_DIRNAME)
    _remove_empty_tree(old / TRASH_DIRNAME)
    return moved


def undo_migration(lib: Path) -> int:
    """기록을 거꾸로 돌려 원래 자리로 되돌린다. 원래 자리에 다른 파일이 생겼으면 아무것도 옮기지 않고 거부한다."""
    ledger = lib / LEDGER_NAME
    if not ledger.is_file():
        return 0
    entries = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    todo = [(Path(e["dst"]), Path(e["src"])) for e in reversed(entries) if Path(e["dst"]).is_file()]
    for dst, src in todo:
        if src.exists() and not _same_content(dst, src):
            raise MigrationConflict(str(src))
    moved = 0
    for dst, src in todo:
        if src.exists():
            dst.unlink()
        else:
            _move_file(dst, src)
        moved += 1
    ledger.unlink()
    return moved
