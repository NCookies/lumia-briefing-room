"""클립 저장 폴더를 바꿀 때 기존 클립 영상을 새 폴더로 옮긴다.

클립 정보(json·썸네일 등)는 앱 데이터 library 에 있어 따라 옮기지 않는다. 영상 파일은 하위 폴더 구조 그대로 옮기고, 재생용 변환 영상
(`.proxy`)은 다시 만들 수 있지만 같이 옮긴다. 영상이 아닌 파일(사용자가 같은 폴더에 둔 문서 등)은 건드리지 않는다.
"""

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lumia_briefing_room.pipeline.clip_files import walk_videos

SIDE_DIRNAMES = (".proxy",)


class MoveError(Exception):
    """옮길 수 없는 이유를 사용자에게 그대로 보여 줄 수 있는 문장으로 담는다."""


def _is_inside(child: Path, parent: Path) -> bool:
    return child != parent and parent in child.parents


@dataclass
class MovePlan:
    old: Path
    pairs: list[tuple[Path, Path]]
    clips: int
    total_bytes: int


def plan_move(old: Path, new: Path) -> MovePlan | None:
    """옮길 파일 목록을 만든다. 옮길 게 없으면(같은 폴더·없는 폴더) None, 옮길 수 없으면 MoveError.

    같은 이름의 파일이 이미 new 에 있으면 아무것도 옮기기 전에 거부한다.
    """
    old, new = old.resolve(), new.resolve()
    if old == new:
        return None
    if _is_inside(new, old) or _is_inside(old, new):
        raise MoveError("새 폴더는 기존 폴더의 안쪽이거나 바깥쪽일 수 없습니다")
    if not old.is_dir():
        return None

    pairs: list[tuple[Path, Path]] = []
    clips = 0
    for video in walk_videos([old]):
        pairs.append((video, new / video.relative_to(old)))
        clips += 1
    for name in SIDE_DIRNAMES:
        side = old / name
        if side.is_dir():
            for file in sorted(p for p in side.rglob("*") if p.is_file()):
                pairs.append((file, new / file.relative_to(old)))

    clashes = [dst.name for _, dst in pairs if dst.exists()]
    if clashes:
        raise MoveError(f"새 폴더에 같은 이름의 파일이 이미 있습니다: {', '.join(clashes[:3])}")
    return MovePlan(old=old, pairs=pairs, clips=clips, total_bytes=sum(src.stat().st_size for src, _ in pairs))


def execute_move(plan: MovePlan, progress: Callable[[int, int], None] | None = None) -> int:
    """계획대로 옮기고 옮긴 클립 수를 돌려준다. progress(옮긴 바이트, 전체 바이트)는 파일 하나를 옮길 때마다 부른다.

    도중에 실패해도 남은 것만 old 에 있으므로 다시 시도하면 이어서 옮겨진다.
    """
    done = 0
    if progress is not None:
        progress(0, plan.total_bytes)
    for src, dst in plan.pairs:
        size = src.stat().st_size
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        done += size
        if progress is not None:
            progress(done, plan.total_bytes)

    for name in SIDE_DIRNAMES:
        _remove_empty_tree(plan.old / name)
    return plan.clips


def move_clips_dir(old: Path, new: Path, progress: Callable[[int, int], None] | None = None) -> int:
    plan = plan_move(old, new)
    return 0 if plan is None else execute_move(plan, progress)


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
