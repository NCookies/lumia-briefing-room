"""클립 정리 탭이 다루는 "클립 폴더"의 실제 폴더 조작. (plan-fullvideo.md §3.9)

앱은 클립을 분류하지 않는다 - 사용자가 폴더를 만들고 옮기는 것을 돕는 인터페이스만 준다. 모든 경로는 클립 폴더 기준 상대 경로(`/` 구분)이고,
클립 폴더 밖으로 나가는 경로(`..`·절대 경로·드라이브·심볼릭 링크)와 `.` 으로 시작하는 폴더(앱 작업·캐시)는 거부한다.
옛 경로 모드는 클립 폴더가 둘(스팀 녹화·영상 파일)이라 가상 최상위 아래에 두 폴더가 놓인다.
"""

from __future__ import annotations

import errno
import os
import shutil
from collections.abc import Sequence
from pathlib import Path

from lumia_briefing_room.api.export import is_valid_folder_name
from lumia_briefing_room.pipeline.clip_files import is_temp_video, move_file, walk_videos
from lumia_briefing_room.video_formats import VIDEO_EXTENSIONS


class LibraryError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 문장. `status` 는 HTTP 상태."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS and not is_temp_video(path.name)


def _remove_empty_tree(folder: Path) -> None:
    for child in sorted((p for p in folder.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            child.rmdir()
        except OSError:
            pass
    try:
        folder.rmdir()
    except OSError:
        pass


def move_tree(src: Path, dst: Path) -> None:
    """폴더를 통째로 옮긴다. 같은 드라이브면 이름 바꾸기, 다르면 파일마다 복사한 뒤 원본을 지운다."""
    try:
        os.rename(src, dst)
        return
    except OSError as exc:
        if exc.errno not in (errno.EXDEV, 18) and src.drive == dst.drive:
            raise
    for current, _, files in os.walk(src):
        for name in files:
            path = Path(current) / name
            move_file(path, dst / path.relative_to(src), overwrite=False)
    dst.mkdir(parents=True, exist_ok=True)
    for current, dirs, _ in os.walk(src):
        for name in dirs:
            (dst / (Path(current) / name).relative_to(src)).mkdir(parents=True, exist_ok=True)
    _remove_empty_tree(src)


class LibraryRoots:
    def __init__(self, entries: Sequence[tuple[str, Path]], *, single: bool):
        self.entries = list(entries)
        self.single = single

    def _parts(self, rel: str) -> list[str]:
        if "\\" in rel or ":" in rel or rel.startswith("/"):
            raise LibraryError("올바르지 않은 경로입니다")
        parts = [p for p in rel.split("/") if p]
        for part in parts:
            if part in (".", "..") or part.startswith("."):
                raise LibraryError("올바르지 않은 경로입니다")
        return parts

    def is_virtual(self, rel: str) -> bool:
        return not self.single and not self._parts(rel)

    def resolve(self, rel: str) -> Path:
        parts = self._parts(rel)
        if self.single:
            base, rest = self.entries[0][1], parts
        else:
            if not parts:
                raise LibraryError("이 위치는 폴더가 아닙니다")
            named = dict(self.entries)
            if parts[0] not in named:
                raise LibraryError("찾을 수 없는 폴더입니다", 404)
            base, rest = named[parts[0]], parts[1:]
        path = base.joinpath(*rest)
        try:
            inside = path.resolve() == base.resolve() or base.resolve() in path.resolve().parents
        except OSError:
            inside = False
        if not inside:
            raise LibraryError("클립 폴더 밖은 다룰 수 없습니다")
        return path

    def rel_of(self, path: Path) -> str:
        for name, base in self.entries:
            try:
                parts = path.relative_to(base).parts
            except ValueError:
                continue
            return "/".join(parts if self.single else (name, *parts))
        raise LibraryError("클립 폴더 밖의 경로입니다")

    def _count(self, folder: Path) -> int:
        return sum(1 for _ in walk_videos([folder]))

    def list_folders(self, rel: str) -> list[dict]:
        if self.is_virtual(rel):
            return [{"name": name, "rel": name, "clipCount": self._count(base)} for name, base in self.entries]
        folder = self.resolve(rel)
        if not folder.is_dir():
            raise LibraryError("찾을 수 없는 폴더입니다", 404)
        found = []
        for child in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
            if child.is_dir() and not child.name.startswith("."):
                found.append({"name": child.name, "rel": self.rel_of(child), "clipCount": self._count(child)})
        return found

    def list_folder(self, rel: str) -> tuple[list[dict], list[Path]]:
        folders = self.list_folders(rel)
        if self.is_virtual(rel):
            return folders, []
        folder = self.resolve(rel)
        videos = sorted((p for p in folder.iterdir() if p.is_file() and _is_video(p)), key=lambda p: p.name.casefold())
        return folders, videos

    def _checked_name(self, name: str) -> str:
        name = name.strip()
        if not name or name.startswith(".") or not is_valid_folder_name(name):
            raise LibraryError("이름에 쓸 수 없는 문자가 들어 있거나 비어 있습니다")
        return name

    def make_folder(self, parent_rel: str, name: str) -> str:
        if self.is_virtual(parent_rel):
            raise LibraryError("여기에는 폴더를 만들 수 없습니다. 스팀 녹화·영상 파일 폴더 안에서 만드세요")
        parent = self.resolve(parent_rel)
        if not parent.is_dir():
            raise LibraryError("찾을 수 없는 폴더입니다", 404)
        target = parent / self._checked_name(name)
        if target.exists():
            raise LibraryError("같은 이름이 이미 있습니다", 409)
        target.mkdir()
        return self.rel_of(target)

    def _is_top_entry(self, rel: str) -> bool:
        return not self.single and len(self._parts(rel)) == 1

    def ensure_entry(self, rel: str) -> None:
        """클립 폴더 자체(또는 옛 경로 모드의 스팀 녹화·영상 파일 폴더)가 아니라 그 안의 항목이어야 한다."""
        if not self._parts(rel) or self._is_top_entry(rel):
            raise LibraryError("이 폴더는 지우거나 옮길 수 없습니다")

    def rename(self, rel: str, new_name: str) -> str:
        if not self._parts(rel) or self._is_top_entry(rel):
            raise LibraryError("이 폴더의 이름은 바꿀 수 없습니다")
        path = self.resolve(rel)
        if not path.exists():
            raise LibraryError("찾을 수 없습니다", 404)
        new_name = self._checked_name(new_name)
        if path.is_file():
            if new_name.lower().endswith(path.suffix.lower()):
                new_name = new_name[: -len(path.suffix)]
            new_name = self._checked_name(new_name) + path.suffix
        target = path.with_name(new_name)
        if target.exists() and target != path:
            raise LibraryError("같은 이름이 이미 있습니다", 409)
        if target != path:
            os.rename(path, target)
        return self.rel_of(target)

    def move(self, rels: Sequence[str], dest_rel: str) -> list[str]:
        if self.is_virtual(dest_rel):
            raise LibraryError("여기로는 옮길 수 없습니다. 스팀 녹화·영상 파일 폴더 안으로 옮기세요")
        dest = self.resolve(dest_rel)
        if not dest.is_dir():
            raise LibraryError("옮길 폴더를 찾을 수 없습니다", 404)
        pairs: list[tuple[Path, Path]] = []
        names: set[str] = set()
        for rel in rels:
            if not self._parts(rel) or self._is_top_entry(rel):
                raise LibraryError("이 폴더는 옮길 수 없습니다")
            src = self.resolve(rel)
            if not src.exists():
                raise LibraryError("찾을 수 없습니다", 404)
            if src.parent.resolve() == dest.resolve():
                continue
            if src.is_dir() and (dest.resolve() == src.resolve() or src.resolve() in dest.resolve().parents):
                raise LibraryError("폴더를 그 폴더 안으로 옮길 수 없습니다")
            target = dest / src.name
            if target.exists() or src.name.casefold() in names:
                raise LibraryError(f"옮길 폴더에 같은 이름이 이미 있습니다: {src.name}", 409)
            names.add(src.name.casefold())
            pairs.append((src, target))
        moved = []
        for src, target in pairs:
            if src.is_dir():
                move_tree(src, target)
            else:
                move_file(src, target, overwrite=False)
            moved.append(self.rel_of(target))
        return moved

    def collect_videos(self, rels: Sequence[str]) -> list[Path]:
        found: list[Path] = []
        for rel in rels:
            path = self.resolve(rel)
            if path.is_dir():
                found.extend(walk_videos([path]))
            elif path.is_file() and _is_video(path):
                found.append(path)
        return found
