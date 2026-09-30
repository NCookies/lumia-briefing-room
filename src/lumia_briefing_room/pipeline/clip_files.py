"""클립 영상(mp4)이 어디 있는지 찾는다. 클립 정보(json)는 library 폴더에, 영상은 저장 폴더의 클립 폴더에 따로 있다. (plan-fullvideo.md §3.10a)

영상은 정보 파일 옆(옛 구조·작업 폴더) 또는 클립 영상 자리들 아래(하위 폴더 포함)에서 파일 이름 줄기(`<클립 ID>`)로 찾는다.
`.` 으로 시작하는 폴더(작업 폴더·캐시)와 만들다 만 임시 파일은 건너뛴다.
"""

from __future__ import annotations

import errno
import os
import shutil
from collections.abc import Iterable
from pathlib import Path

from lumia_briefing_room.video_formats import VIDEO_EXTENSIONS

TEMP_MARKERS = (".tmp.", ".replace.", ".trim.", ".part")


def is_temp_video(name: str) -> bool:
    lowered = name.lower()
    return any(m in lowered for m in TEMP_MARKERS) or lowered.endswith(".part")


def walk_videos(roots: Iterable[Path]) -> Iterable[Path]:
    """클립 영상 자리 아래의 영상 파일 전부. 없는 폴더는 건너뛴다(드라이브를 뺀 경우)."""
    for root in roots:
        if not root.is_dir():
            continue
        for current, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for name in sorted(files):
                path = Path(current) / name
                if path.suffix.lower() in VIDEO_EXTENSIONS and not is_temp_video(name):
                    yield path


def index_videos(meta_dir: Path, roots: Iterable[Path]) -> dict[str, Path]:
    """파일 이름 줄기 → 영상 경로. 정보 파일 옆 영상이 먼저이고, 같은 이름이 둘이면 경로순으로 앞선 것."""
    found: dict[str, Path] = {}
    beside = {p.stem: p for p in meta_dir.glob("*.mp4") if not is_temp_video(p.name)} if meta_dir.is_dir() else {}
    found.update(beside)
    for path in walk_videos(roots):
        found.setdefault(path.stem, path)
    return found


def find_video(meta_dir: Path, clip_id: str, roots: Iterable[Path]) -> Path | None:
    beside = meta_dir / f"{clip_id}.mp4"
    if beside.is_file():
        return beside
    for path in walk_videos(roots):
        if path.stem == clip_id:
            return path
    return None


def move_file(src: Path, dst: Path, *, overwrite: bool = True) -> None:
    """파일 하나를 옮긴다. 같은 드라이브면 이름 바꾸기, 다르면 `<이름>.part` 로 복사한 뒤 이름을 바꾸고 원본을 지운다.

    복사 도중 꺼져도 `.part` 는 클립으로 보이지 않는다. `overwrite=False` 면 목적지가 있을 때 `FileExistsError`.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite and dst.exists():
        raise FileExistsError(str(dst))
    try:
        os.replace(src, dst)
        return
    except OSError as exc:
        if exc.errno not in (errno.EXDEV, 18) and dst.parent.drive == src.parent.drive:
            raise
    part = dst.with_name(dst.name + ".part")
    try:
        shutil.copyfile(src, part)
        if part.stat().st_size != src.stat().st_size:
            raise OSError(f"복사한 크기가 다르다: {src}")
        os.replace(part, dst)
    finally:
        part.unlink(missing_ok=True)
    src.unlink()


def commit_staged_clips(staging: Path, meta_root: Path, video_root: Path) -> list[Path]:
    """작업 폴더에 만든 클립을 제자리로 옮기고 작업 폴더를 지운다. 영상 → 썸네일·이미지 → json 순서라 json 이 보일 때는 나머지가 다 있다.

    작업 폴더 맨 위의 영상 파일은 `video_root` 로, 나머지는 상대 구조를 유지해 `meta_root`(정보 폴더)로 간다. 옮긴 json 경로를 돌려준다.
    """
    files = [p for p in sorted(staging.rglob("*")) if p.is_file()]

    def rank(p: Path) -> tuple[int, str]:
        if p.parent == staging and p.suffix.lower() in VIDEO_EXTENSIONS:
            return 0, p.name
        return (2 if p.suffix == ".json" else 1), str(p)

    moved_json: list[Path] = []
    for path in sorted(files, key=rank):
        if path.parent == staging and path.suffix.lower() in VIDEO_EXTENSIONS:
            move_file(path, video_root / path.name)
            continue
        target = meta_root / path.relative_to(staging)
        move_file(path, target)
        if path.suffix == ".json" and path.parent == staging:
            moved_json.append(target)
    shutil.rmtree(staging, ignore_errors=True)
    return moved_json
