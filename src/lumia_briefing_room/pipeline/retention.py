"""휴지통 기반 삭제/복구 + 자동 정리. (SPEC §7.6)

"삭제는 되돌릴 수 있어야 한다"는 이 절의 전제다 — 그래서 즉시 지우지 않고
휴지통으로 옮긴 뒤, 유예 기간이 지난 것만 purge_expired() 가 실제로 지운다.
"""

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lumia_briefing_room.config import RetentionConfig

_default_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


def _read_meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_meta(meta: dict, path: Path) -> None:
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _clip_files(meta_path: Path, meta: dict) -> list[Path]:
    """메타데이터 하나에 딸린 파일들(mp4, 썸네일) — 메타데이터 자신은 제외."""
    files = [meta_path.with_suffix(".mp4")]
    thumb = meta.get("thumbnailPath")
    if thumb:
        files.append(Path(thumb))
    return [f for f in files if f.exists()]


def _move_clip(meta_path: Path, dest_root: Path, src_root: Path) -> Path:
    """meta_path 와 딸린 파일들을 dest_root 아래로, src_root 기준 상대 구조를 유지하며 옮긴다."""
    meta = _read_meta(meta_path)
    files = _clip_files(meta_path, meta) + [meta_path]

    moved_meta_path = meta_path
    for f in files:
        try:
            rel = f.relative_to(src_root)
        except ValueError:
            rel = Path(f.name)
        dest = dest_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(dest))
        if f == meta_path:
            moved_meta_path = dest

    return moved_meta_path


def trash_clip(
    meta_path: Path, trash_dir: Path, *, now: Callable[[], datetime] = _default_now
) -> Path:
    """클립을 휴지통으로 옮기고 deletedAt 을 채운다. 새 메타데이터 경로를 반환."""
    clips_dir = meta_path.parent
    moved_path = _move_clip(meta_path, trash_dir, clips_dir)

    meta = _read_meta(moved_path)
    meta["deletedAt"] = now().isoformat()
    thumb = meta.get("thumbnailPath")
    if thumb:
        old_thumb = Path(thumb)
        try:
            rel = old_thumb.relative_to(clips_dir)
            meta["thumbnailPath"] = str(trash_dir / rel)
        except ValueError:
            pass
    _write_meta(meta, moved_path)

    return moved_path


def restore_clip(trashed_meta_path: Path, clips_dir: Path) -> Path:
    """휴지통에서 원래 위치로 되돌리고 deletedAt 을 지운다. 새 메타데이터 경로를 반환."""
    trash_dir = trashed_meta_path.parent
    moved_path = _move_clip(trashed_meta_path, clips_dir, trash_dir)

    meta = _read_meta(moved_path)
    meta["deletedAt"] = None
    thumb = meta.get("thumbnailPath")
    if thumb:
        old_thumb = Path(thumb)
        try:
            rel = old_thumb.relative_to(trash_dir)
            meta["thumbnailPath"] = str(clips_dir / rel)
        except ValueError:
            pass
    _write_meta(meta, moved_path)

    return moved_path


def purge_expired(
    trash_dir: Path, *, trash_days: int, now: Callable[[], datetime] = _default_now
) -> list[Path]:
    """유예 기간이 지난 클립을 실제로(되돌릴 수 없게) 지운다. 지운 메타데이터 경로 목록."""
    if not trash_dir.exists():
        return []

    purged: list[Path] = []
    cutoff = now() - timedelta(days=trash_days)

    for meta_path in trash_dir.glob("*.json"):
        meta = _read_meta(meta_path)
        deleted_at = meta.get("deletedAt")
        if not deleted_at:
            continue
        if datetime.fromisoformat(deleted_at) > cutoff:
            continue

        for f in _clip_files(meta_path, meta):
            f.unlink(missing_ok=True)
        meta_path.unlink()
        purged.append(meta_path)

    return purged


def is_protected(meta: dict, cfg: RetentionConfig) -> bool:
    """SPEC §7.6: 고정(pin)했거나 보호 태그가 붙은 클립은 자동 정리 대상이 아니다."""
    if cfg.protect_pinned and meta.get("pinned"):
        return True
    if set(meta.get("tags", [])) & set(cfg.protect_tags):
        return True
    return False


@dataclass(frozen=True)
class _Candidate:
    meta: dict
    age_days: float
    size_bytes: int


def select_for_auto_clean(
    metas: list[dict], cfg: RetentionConfig, *, now: Callable[[], datetime] = _default_now
) -> list[dict]:
    """SPEC §7.6: maxAgeDays/maxTotalGB/maxCount 를 넘는 만큼, 보호되지 않은 것 중
    오래된 것부터 고른다. auto_clean_enabled 가 꺼져 있거나 한도가 하나도 없으면 빈 리스트.

    호출 규약: 각 meta 는 "_created_at"(datetime) 과 "_size_bytes"(int) 를 들고 있어야
    한다 — 실제 클립 스캔 계층(아직 안 만듦)이 파일 mtime/크기로 채워 넣는다.
    """
    if not cfg.auto_clean_enabled:
        return []
    if cfg.max_age_days is None and cfg.max_total_gb is None and cfg.max_count is None:
        return []

    current = now()
    candidates = [
        _Candidate(
            meta=m,
            age_days=(current - m["_created_at"]).total_seconds() / 86400,
            size_bytes=m["_size_bytes"],
        )
        for m in metas
        if not is_protected(m, cfg)
    ]
    candidates.sort(key=lambda c: c.age_days, reverse=True)  # 오래된 것부터

    selected: list[_Candidate] = []
    remaining = list(candidates)

    if cfg.max_age_days is not None:
        for c in list(remaining):
            if c.age_days > cfg.max_age_days:
                selected.append(c)
                remaining.remove(c)

    if cfg.max_count is not None:
        kept = [c for c in candidates if c not in selected]
        excess = len(kept) - cfg.max_count
        for c in kept:
            if excess <= 0:
                break
            if c not in selected:
                selected.append(c)
                if c in remaining:
                    remaining.remove(c)
                excess -= 1

    if cfg.max_total_gb is not None:
        max_bytes = cfg.max_total_gb * 1024**3
        kept = [c for c in candidates if c not in selected]
        total = sum(c.size_bytes for c in kept)
        for c in kept:
            if total <= max_bytes:
                break
            selected.append(c)
            total -= c.size_bytes

    order = {id(c): i for i, c in enumerate(candidates)}
    selected.sort(key=lambda c: order[id(c)])
    return [c.meta for c in selected]
