"""전송 진행 상태(마지막 성공 시각, 다음 시도 시각, 연속 실패 횟수, 이미 보낸 라벨의 내용 지문)를 파일에 보관한다.

파일이 없거나 깨져 있으면 처음 상태로 시작한다(이미 보낸 라벨을 다시 보낼 수는 있지만 서버가 같은 clipKey 로 덮어쓰므로 중복은 생기지 않는다).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from lumia_briefing_room.config import _default_local_appdata

KINDS = ("labels", "logs")
_LOCK = threading.RLock()


def default_state_path() -> Path:
    return _default_local_appdata() / "LumiaBriefingRoom" / "telemetry_state.json"


def _fresh() -> dict:
    return {kind: {"lastSuccess": None, "nextAttempt": 0.0, "failures": 0} for kind in KINDS} | {"digests": {}}


class TelemetryState:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> dict:
        state = _fresh()
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return state
        if isinstance(stored, dict):
            for kind in KINDS:
                if isinstance(stored.get(kind), dict):
                    state[kind].update(stored[kind])
            if isinstance(stored.get("digests"), dict):
                state["digests"] = {str(k): str(v) for k, v in stored["digests"].items()}
        return state

    def _save(self, state: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def kind(self, name: str) -> dict:
        with _LOCK:
            return dict(self._load()[name])

    def update(self, name: str, **fields) -> None:
        with _LOCK:
            state = self._load()
            state[name].update(fields)
            self._save(state)

    def digests(self) -> dict[str, str]:
        with _LOCK:
            return dict(self._load()["digests"])

    def remember(self, digests: dict[str, str]) -> None:
        with _LOCK:
            state = self._load()
            state["digests"].update(digests)
            self._save(state)

    def reset(self) -> None:
        with _LOCK:
            self._save(_fresh())
