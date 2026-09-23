"""클립 저장 폴더를 바꿀 때 기존 클립을 새 폴더로 옮긴다.

클립 목록은 설정된 폴더만 읽으므로, 폴더만 바꾸면 이전 클립이 화면에서 사라진다.
클립 폴더가 아닌 파일(사용자가 같은 폴더에 둔 다른 영상 등)은 건드리지 않는다.
"""

import shutil
from pathlib import Path

from lumia_briefing_room.pipeline.clip_assets import THUMBS_DIRNAME, TRASH_DIRNAME
from lumia_briefing_room.pipeline.game_records import RECORDS_DIRNAME
from lumia_briefing_room.pipeline.label_archive import ARCHIVE_DIRNAME

SIDE_DIRNAMES = (THUMBS_DIRNAME, TRASH_DIRNAME, ".proxy", RECORDS_DIRNAME, ARCHIVE_DIRNAME)


class MoveError(Exception):
    """옮길 수 없는 이유를 사용자에게 그대로 보여 줄 수 있는 문장으로 담는다."""


def _is_inside(child: Path, parent: Path) -> bool:
    return child != parent and parent in child.parents


def _plan(old: Path, new: Path) -> tuple[list[tuple[Path, Path]], int]:
    pairs: list[tuple[Path, Path]] = []
    clips = 0
    for meta in sorted(old.glob("*.json")):
        video = meta.with_suffix(".mp4")
        if video.exists():
            pairs.append((video, new / video.name))
        pairs.append((meta, new / meta.name))
        clips += 1
    for name in SIDE_DIRNAMES:
        side = old / name
        if side.is_dir():
            for file in sorted(p for p in side.rglob("*") if p.is_file()):
                pairs.append((file, new / file.relative_to(old)))
    return pairs, clips


def move_clips_dir(old: Path, new: Path) -> int:
    """old 폴더의 클립과 딸린 폴더를 new 로 옮기고 옮긴 클립 수를 돌려준다.

    이미 같은 이름의 파일이 new 에 있으면 아무것도 옮기기 전에 거부한다. 도중에 실패해도 남은 것만 old 에 있으므로 다시 시도하면 이어서 옮겨진다.
    """
    old, new = old.resolve(), new.resolve()
    if old == new:
        return 0
    if _is_inside(new, old) or _is_inside(old, new):
        raise MoveError("새 폴더는 기존 폴더의 안쪽이거나 바깥쪽일 수 없습니다")
    if not old.is_dir():
        return 0

    pairs, clips = _plan(old, new)
    clashes = [dst.name for _, dst in pairs if dst.exists()]
    if clashes:
        raise MoveError(f"새 폴더에 같은 이름의 파일이 이미 있습니다: {', '.join(clashes[:3])}")

    for src, dst in pairs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

    for name in SIDE_DIRNAMES:
        _remove_empty_tree(old / name)
    return clips


def _remove_empty_tree(path: Path) -> None:
    if not path.is_dir():
        return
    for child in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if child.is_dir():
            try:
                child.rmdir()
            except OSError:
                pass
    try:
        path.rmdir()
    except OSError:
        pass
