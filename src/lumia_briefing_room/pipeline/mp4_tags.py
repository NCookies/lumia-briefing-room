"""클립 영상(mp4) 안에 클립 ID(`clipUid`)를 넣고 읽는다. (plan-fullvideo.md §3.10a-(4))

탐색기에서 이름을 바꾸거나 다른 폴더로 옮겨도 영상 안의 ID 로 같은 클립을 알아보고 정보(제목·태그·라벨·게임)를 다시 잇는다.
쓰기: `ffmpeg -c copy -metadata comment=lumia:clipUid=<ID>` — mp4 표준 `comment`(©cmt) 태그라 `-movflags use_metadata_tags` 없이 들어가고,
자르기(`-map 0 -c copy`)와 복사·이름 바꾸기 뒤에도 남는다(사용자 정의 키는 그 옵션 없이는 조용히 버려진다).
읽기: ffprobe 는 파일당 70ms 라 mp4 상위 박스를 훑어 `moov/udta/meta/ilst/©cmt` 만 읽는다(1ms). 결과는 경로·크기·수정 시각으로 캐시한다.
"""

from __future__ import annotations

import struct
import threading
from pathlib import Path

TAG_PREFIX = "lumia:clipUid="
_MAX_MOOV = 64 * 1024 * 1024
_cache: dict[str, tuple[int, int, str | None]] = {}
_lock = threading.Lock()


def uid_metadata_args(uid: str) -> list[str]:
    return ["-metadata", f"comment={TAG_PREFIX}{uid}"]


def _children(buf: bytes, start: int, end: int):
    i = start
    while i + 8 <= end:
        size, kind = struct.unpack(">I4s", buf[i:i + 8])
        header = 8
        if size == 1:
            if i + 16 > end:
                return
            size = struct.unpack(">Q", buf[i + 8:i + 16])[0]
            header = 16
        elif size == 0:
            size = end - i
        if size < header or i + size > end:
            return
        yield kind, i + header, i + size
        i += size


def _comment_from_moov(moov: bytes) -> str | None:
    for kind, s, e in _children(moov, 0, len(moov)):
        if kind != b"udta":
            continue
        for k2, s2, e2 in _children(moov, s, e):
            if k2 != b"meta":
                continue
            for k3, s3, e3 in _children(moov, s2 + 4, e2):
                if k3 != b"ilst":
                    continue
                for k4, s4, e4 in _children(moov, s3, e3):
                    if k4 != b"\xa9cmt":
                        continue
                    for k5, s5, e5 in _children(moov, s4, e4):
                        if k5 == b"data" and e5 - s5 >= 8:
                            return moov[s5 + 8:e5].decode("utf-8", errors="replace")
    return None


def _parse_uid(path: Path) -> str | None:
    try:
        with path.open("rb") as f:
            size = f.seek(0, 2)
            pos = 0
            while pos + 8 <= size:
                f.seek(pos)
                head = f.read(16)
                box_size, kind = struct.unpack(">I4s", head[:8])
                header = 8
                if box_size == 1:
                    if len(head) < 16:
                        return None
                    box_size = struct.unpack(">Q", head[8:16])[0]
                    header = 16
                elif box_size == 0:
                    box_size = size - pos
                if box_size < header or pos + box_size > size:
                    return None
                if kind == b"moov":
                    if box_size - header > _MAX_MOOV:
                        return None
                    f.seek(pos + header)
                    comment = _comment_from_moov(f.read(box_size - header))
                    if comment and comment.startswith(TAG_PREFIX):
                        return comment[len(TAG_PREFIX):].strip() or None
                    return None
                pos += box_size
    except (OSError, struct.error):
        return None
    return None


def read_clip_uid(path: Path) -> str | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    key = str(path)
    with _lock:
        hit = _cache.get(key)
    if hit and hit[0] == stat.st_size and hit[1] == stat.st_mtime_ns:
        return hit[2]
    uid = _parse_uid(path)
    with _lock:
        _cache[key] = (stat.st_size, stat.st_mtime_ns, uid)
    return uid
