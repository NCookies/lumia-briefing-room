"""클립 카테고리 = `clips\` 바로 아래 실제 폴더. (plan-fullvideo.md §3.9)

기본 칸 `보관함`(직접 보관한 클립), `자동 보관`(앱이 자동으로 만든 클립)은 폴더가 없어도 항상 목록에 있다.
이름 검사·폴더 만들기는 클립 정리 탭과 같은 규칙(`LibraryRoots`)을 쓴다. 옛 경로 모드에는 카테고리가 없다.
"""

from __future__ import annotations

from pathlib import Path

from lumia_briefing_room.config import ARCHIVE_FOLDER, AUTO_ARCHIVE_FOLDER, Config, resolve_paths, uses_legacy_layout
from lumia_briefing_room.pipeline.library_fs import LibraryError, LibraryRoots


def enabled(cfg: Config) -> bool:
    return not uses_legacy_layout(cfg.paths)


def clips_root(cfg: Config) -> Path:
    return resolve_paths(cfg.paths).clips_root


def _roots(cfg: Config) -> LibraryRoots:
    return LibraryRoots([("클립", clips_root(cfg))], single=True)


def checked_name(cfg: Config, name: object) -> str:
    text = str(name or "").strip()
    _roots(cfg)._checked_name(text)
    return text


def category_folder(cfg: Config, name: str | None, *, create: bool = False) -> Path:
    """카테고리 이름 → 폴더. `name` 이 없으면 기본 칸 `보관함`."""
    folder = clips_root(cfg) / checked_name(cfg, name or ARCHIVE_FOLDER)
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def create_category(cfg: Config, name: object) -> str:
    text = checked_name(cfg, name)
    folder = clips_root(cfg) / text
    if folder.exists() or text in (ARCHIVE_FOLDER, AUTO_ARCHIVE_FOLDER):
        raise LibraryError("같은 이름의 카테고리가 이미 있습니다", 409)
    folder.mkdir(parents=True)
    return text


def category_of(cfg: Config, video: Path) -> str | None:
    """영상이 놓인 카테고리(`clips\` 바로 아래 폴더 이름). `clips\` 바로 밑이거나 밖이면 None."""
    try:
        parts = video.relative_to(clips_root(cfg)).parts
    except ValueError:
        return None
    return parts[0] if len(parts) > 1 else None


def category_names(cfg: Config) -> list[str]:
    """`보관함` → 사용자 카테고리(이름순) → `자동 보관`."""
    root = clips_root(cfg)
    found = []
    if root.is_dir():
        found = [p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")]
    users = sorted((n for n in found if n not in (ARCHIVE_FOLDER, AUTO_ARCHIVE_FOLDER)), key=str.casefold)
    return [ARCHIVE_FOLDER, *users, AUTO_ARCHIVE_FOLDER]
