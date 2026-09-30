"""클립 영상(mp4)이 어디 있는지 찾는다. 클립 정보(json)는 library 폴더에, 영상은 저장 폴더의 클립 폴더에 따로 있다. (plan-fullvideo.md §3.10a)

영상은 정보 파일 옆(옛 구조·작업 폴더) 또는 클립 영상 자리들 아래(하위 폴더 포함)에서 파일 이름 줄기(`<클립 ID>`)로 찾는다.
`.` 으로 시작하는 폴더(작업 폴더·캐시)와 만들다 만 임시 파일은 건너뛴다.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from lumia_briefing_room.pipeline.mp4_tags import read_clip_uid
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


def _beside(meta_dir: Path) -> list[Path]:
    if not meta_dir.is_dir():
        return []
    return sorted(p for p in meta_dir.glob("*.mp4") if p.is_file() and not is_temp_video(p.name))


_fp_cache: dict[str, tuple[int, int, str]] = {}


def content_fingerprint(path: Path) -> str:
    """파일 크기 + 앞·뒤 1MiB 해시(영상 파일 분석의 `vodId` 와 같은 방식). 내용으로 식별하므로 옮기고 이름을 바꿔도 같다."""
    from lumia_briefing_room.pipeline.vod_store import vod_id

    stat = path.stat()
    hit = _fp_cache.get(str(path))
    if hit and hit[0] == stat.st_size and hit[1] == stat.st_mtime_ns:
        return hit[2]
    value = vod_id(path)
    _fp_cache[str(path)] = (stat.st_size, stat.st_mtime_ns, value)
    return value


def short_hash(path: Path) -> str:
    return hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:6]


@dataclass(frozen=True)
class UnknownVideo:
    id: str
    path: Path


@dataclass
class LinkResult:
    primary: dict[tuple[Path, str], Path]
    extras: list[tuple[Path, str, str, Path]]  # (정보 폴더, 표시 ID `<ID>~<해시>`, 원래 ID, 영상)
    unlinked: list[Path]


def link_all(
    libraries: Sequence[tuple[Path, Sequence[tuple[str, dict]]]], roots: Iterable[Path]
) -> LinkResult:
    """클립 정보(json)와 영상 파일을 잇는다. 순서: ① 영상 안 `clipUid` 태그 ② (태그 없는 영상만) 파일 이름 줄기 ③ (태그 없는 영상만) 정보에
    기록된 지문(`videoFingerprint`, 크기가 같은 영상만 읽는다). 같은 ID 태그가 붙은 영상이 여럿이면 경로순 첫째는 원래 ID, 나머지는 `<ID>~<해시>`."""
    roots = tuple(roots)
    videos: list[Path] = []
    seen: set[Path] = set()
    for meta_dir, _ in libraries:
        for path in _beside(meta_dir):
            if path not in seen:
                seen.add(path)
                videos.append(path)
    for path in walk_videos(roots):
        if path not in seen:
            seen.add(path)
            videos.append(path)
    uids = {path: read_clip_uid(path) for path in videos}
    by_uid: dict[str, list[Path]] = {}
    for path in videos:
        if uids[path]:
            by_uid.setdefault(uids[path], []).append(path)

    primary: dict[tuple[Path, str], Path] = {}
    extras: list[tuple[Path, str, str, Path]] = []
    claimed: set[Path] = set()
    for meta_dir, items in libraries:
        for clip_id, meta in items:
            found = by_uid.get(meta.get("clipUid") or "")
            if not found:
                continue
            primary[(meta_dir, clip_id)] = found[0]
            extras.extend((meta_dir, f"{clip_id}~{short_hash(p)}", clip_id, p) for p in found[1:])
            claimed.update(found)

    untagged = [p for p in videos if not uids[p]]
    stems: dict[str, Path] = {}
    for path in untagged:
        stems.setdefault(path.stem, path)
    for meta_dir, items in libraries:
        for clip_id, _ in items:
            path = stems.get(clip_id)
            if (meta_dir, clip_id) not in primary and path is not None and path not in claimed:
                primary[(meta_dir, clip_id)] = path
                claimed.add(path)

    sizes: dict[Path, int] = {}
    for meta_dir, items in libraries:
        for clip_id, meta in items:
            want_size, want_fp = meta.get("videoSizeBytes"), meta.get("videoFingerprint")
            if (meta_dir, clip_id) in primary or not want_fp or not isinstance(want_size, int):
                continue
            for path in untagged:
                if path in claimed:
                    continue
                if path not in sizes:
                    try:
                        sizes[path] = path.stat().st_size
                    except OSError:
                        sizes[path] = -1
                if sizes[path] == want_size and content_fingerprint(path) == want_fp:
                    primary[(meta_dir, clip_id)] = path
                    claimed.add(path)
                    break
    return LinkResult(primary=primary, extras=extras, unlinked=[p for p in videos if p not in claimed])


def load_metas(meta_dir: Path) -> list[tuple[str, dict]]:
    items: list[tuple[str, dict]] = []
    if not meta_dir.is_dir():
        return items
    for path in sorted(meta_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            items.append((path.stem, data))
    return items


def unknown_videos(meta_dirs: Sequence[Path], roots: Iterable[Path]) -> list[UnknownVideo]:
    """어떤 클립 정보와도 안 이어지는 영상(OBS 녹화 등). ID 는 내용 지문(`x_<지문>`)이라 옮겨도 같고, 같은 내용의 복사본은 `~<해시>` 로 구분한다."""
    result = link_all([(d, load_metas(d)) for d in meta_dirs], roots)
    found: list[UnknownVideo] = []
    seen_ids: set[str] = set()
    for path in result.unlinked:
        try:
            base = f"x_{content_fingerprint(path)}"
        except OSError:
            continue
        clip_id = base if base not in seen_ids else f"{base}~{short_hash(path)}"
        seen_ids.add(clip_id)
        found.append(UnknownVideo(clip_id, path))
    return found


def find_unknown(clip_id: str, meta_dirs: Sequence[Path], roots: Iterable[Path]) -> UnknownVideo | None:
    if not clip_id.startswith("x_"):
        return None
    return next((u for u in unknown_videos(meta_dirs, roots) if u.id == clip_id), None)


def find_video(meta_dir: Path, clip_id: str, roots: Iterable[Path], meta: dict | None = None) -> Path | None:
    """`meta` 를 주면 태그·지문으로도 찾고, 안 주면 파일 이름으로만 찾는다."""
    roots = tuple(roots)
    if meta is not None:
        base = clip_id.partition("~")[0]
        result = link_all([(meta_dir, [(base, meta)])], roots)
        if "~" in clip_id:
            return next((p for _, cid, _, p in result.extras if cid == clip_id), None)
        return result.primary.get((meta_dir, base))
    beside = meta_dir / f"{clip_id}.mp4"
    if beside.is_file():
        return beside
    for path in walk_videos(roots):
        if path.stem == clip_id:
            return path
    return None


def find_video_for(meta_path: Path, roots: Iterable[Path]) -> Path | None:
    """정보 파일(json) 하나에 이어지는 영상. 태그·지문·파일 이름 순으로 찾는다."""
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return find_video(meta_path.parent, meta_path.stem, roots)
    return find_video(meta_path.parent, meta_path.stem, roots, meta if isinstance(meta, dict) else None)


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
