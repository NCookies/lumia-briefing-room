"""클립 유니크 ID(`clipUid`). 여러 사용자의 라벨을 합쳐도 겹치지 않게 클립마다 한 번 만들어 메타데이터에 남긴다. (plan-ui.md §0)

파일 이름(클립 ID)은 그대로 두고 메타데이터에 필드만 더한다. 새 클립의 기본 값은 하이픈 없는 무작위 hex 이고,
구간 분할 조각은 부모 값 뒤에 `-<번호>` 를 붙여 계보를 값에서 읽을 수 있게 한다.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from collections.abc import Iterable
from pathlib import Path

log = logging.getLogger("lumia_briefing_room.pipeline.clip_uid")

UID_KEY = "clipUid"
ARCHIVE_DIRNAME = ".labels"
TRASH_DIRNAME = ".trash"


def new_clip_uid() -> str:
    return uuid.uuid4().hex


def piece_uids(parent_uid: str, existing: Iterable[str], count: int) -> list[str]:
    """부모 밑의 다음 조각 값들. 이미 있는 직계 조각(살아 있는 클립·휴지통·보관소)의 최댓값 다음 번호부터 매긴다."""
    direct = re.compile(rf"{re.escape(parent_uid)}-(\d+)")
    highest = 0
    for uid in existing:
        match = direct.fullmatch(uid)
        if match:
            highest = max(highest, int(match.group(1)))
    return [f"{parent_uid}-{highest + i}" for i in range(1, count + 1)]


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json_atomic(path: Path, data: dict) -> None:
    """임시 파일에 쓴 뒤 교체해 반쯤 쓰인 메타데이터가 남지 않게 한다."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def ensure_clip_uid(meta_path: Path) -> str:
    """메타데이터에 `clipUid` 가 없으면 만들어 채우고, 있으면 그대로 돌려준다."""
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    existing = meta.get(UID_KEY)
    if isinstance(existing, str) and existing:
        return existing
    meta[UID_KEY] = new_clip_uid()
    write_json_atomic(meta_path, meta)
    return meta[UID_KEY]


def collect_uids(*folders: Path) -> set[str]:
    uids: set[str] = set()
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in folder.glob("*.json"):
            data = _read(path)
            if isinstance(data, dict) and isinstance(data.get(UID_KEY), str):
                uids.add(data[UID_KEY])
    return uids


def is_clip_meta(data) -> bool:
    return isinstance(data, dict) and ("durationSec" in data or "userLabel" in data)


def _fill_folder(folder: Path, *, inherit_from: list[Path] = ()) -> int:
    if not folder.is_dir():
        return 0
    filled = 0
    for path in sorted(folder.glob("*.json")):
        data = _read(path)
        if not is_clip_meta(data) or data.get(UID_KEY):
            continue
        uid = None
        for source in inherit_from:
            sibling = _read(source / path.name)
            if isinstance(sibling, dict) and sibling.get(UID_KEY):
                uid = sibling[UID_KEY]
                break
        data[UID_KEY] = uid or new_clip_uid()
        try:
            write_json_atomic(path, data)
        except OSError:
            log.warning("clipUid 를 채우지 못했다: %s", path, exc_info=True)
            continue
        filled += 1
    return filled


def backfill_clip_uids(clips_dir: Path) -> int:
    """`clipUid` 가 없는 클립(살아 있는 것·휴지통·라벨 보관소)에만 채운다. 이미 있으면 건너뛰므로 여러 번 돌려도 같고, 도중에 꺼져도 이어서 된다."""
    trash = clips_dir / TRASH_DIRNAME
    filled = _fill_folder(clips_dir) + _fill_folder(trash)
    filled += _fill_folder(clips_dir / ARCHIVE_DIRNAME, inherit_from=[clips_dir, trash])
    return filled
