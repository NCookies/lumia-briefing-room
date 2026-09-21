from __future__ import annotations

import dataclasses
import gzip
import hashlib
import json
import os
import zlib
from pathlib import Path

from lumia_briefing_room.detect.types import FrameState

_HASH_CHUNK = 1024 * 1024
_INDEX_DIR = ".vods"


def vod_id(path: Path) -> str:
    """파일 크기와 앞·뒤 1MiB 의 해시. 경로가 아니라 내용으로 식별해 파일을 옮겨도 같은 영상으로 이어진다."""
    size = path.stat().st_size
    digest = hashlib.sha1(str(size).encode("ascii"))
    with open(path, "rb") as f:
        digest.update(f.read(_HASH_CHUNK))
        if size > _HASH_CHUNK:
            f.seek(max(_HASH_CHUNK, size - _HASH_CHUNK))
            digest.update(f.read(_HASH_CHUNK))
    return digest.hexdigest()[:12]


def _state_to_dict(state: FrameState) -> dict:
    return dataclasses.asdict(state)


def _state_from_dict(data: dict) -> FrameState:
    if data.get("dead_teammates") is not None:
        data = {**data, "dead_teammates": tuple(data["dead_teammates"])}
    return FrameState(**data)


class StateCache:
    """프레임별 판독값을 gzip JSONL 로 이어 쓴다. 분석을 중간에 멈춰도 마지막까지 저장된 시각부터 이어갈 수 있다."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, states: list[FrameState]) -> None:
        if not states:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(json.dumps(_state_to_dict(s), ensure_ascii=False) + "\n" for s in states)
        with gzip.open(self.path, "ab") as f:
            f.write(text.encode("utf-8"))

    def load(self) -> list[FrameState]:
        """끝이 잘려 있으면(쓰다가 종료) 읽을 수 있는 앞부분만 돌려주고 파일을 그 내용으로 고친다."""
        if not self.path.exists():
            return []
        states: list[FrameState] = []
        damaged = False
        try:
            with gzip.open(self.path, "rb") as f:
                for line in f:
                    try:
                        states.append(_state_from_dict(json.loads(line)))
                    except (json.JSONDecodeError, TypeError):
                        damaged = True
                        break
        except (EOFError, OSError, zlib.error):
            damaged = True
        if damaged:
            self.clear()
            self.append(states)
        return states

    def last_t(self) -> float | None:
        states = self.load()
        return states[-1].t if states else None

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


def index_path(clips_dir: Path, vod: str) -> Path:
    return clips_dir / _INDEX_DIR / f"{vod}.json"


def cache_path(clips_dir: Path, vod: str) -> Path:
    return clips_dir / _INDEX_DIR / f"{vod}.states.jsonl.gz"


def save_index(clips_dir: Path, index: dict) -> None:
    path = index_path(clips_dir, index["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_index(clips_dir: Path, vod: str) -> dict | None:
    path = index_path(clips_dir, vod)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
