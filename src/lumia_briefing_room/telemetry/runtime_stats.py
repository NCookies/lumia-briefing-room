"""앱이 돌면서 스스로 재는 값(프록시 인코더·생성 시간, 분석 시간 비율, 하드웨어 디코딩 사용, HEVC 재생 가능 여부).

환경 정보(`Environment`)에 실려 "어떤 PC 에서 게임 중 부하가 큰가", "HEVC 없는 PC 에서 프록시가 얼마나 걸리는가"를 볼 수 있게 한다.
최근 WINDOW 개의 평균만 남기고, 기록하는 일은 어떤 실패도 밖으로 내지 않는다(측정이 앱을 멈추면 안 된다).
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
from pathlib import Path

from lumia_briefing_room import paths
from lumia_briefing_room.config import _default_local_appdata

log = logging.getLogger("lumia_briefing_room.telemetry.runtime_stats")

WINDOW = 20
_LOCK = threading.RLock()


def default_stats_path() -> Path:
    return _default_local_appdata() / paths.app_folder_name() / "runtime_stats.json"


def _positive(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value > 0 else None


def _mean(values: list) -> float | None:
    numbers = [v for v in values if _positive(v) is not None]
    return sum(numbers) / len(numbers) if numbers else None


class RuntimeStats:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def _push(self, data: dict, key: str, value: float) -> None:
        recent = [v for v in data.get(key, []) if isinstance(v, (int, float))]
        data[key] = (recent + [value])[-WINDOW:]

    def record_proxy(self, encoder, seconds) -> None:
        value = _positive(seconds)
        if value is None or not isinstance(encoder, str):
            return
        with _LOCK:
            data = self._load()
            data["proxyEncoder"] = encoder[:32]
            self._push(data, "proxySec", value)
            self._save(data)

    def record_analysis(self, *, process_sec, game_sec, hwaccel: bool) -> None:
        process, game = _positive(process_sec), _positive(game_sec)
        if process is None or game is None:
            return
        with _LOCK:
            data = self._load()
            self._push(data, "analysisRatio", process / game)
            data["hwaccel"] = bool(hwaccel)
            self._save(data)

    def record_hevc(self, playable: bool) -> None:
        with _LOCK:
            data = self._load()
            data["hevcPlayable"] = bool(playable)
            self._save(data)

    def snapshot(self) -> dict:
        with _LOCK:
            data = self._load()
        out: dict = {}
        if isinstance(data.get("proxyEncoder"), str):
            out["proxyEncoder"] = data["proxyEncoder"]
        proxy = _mean(data.get("proxySec", []))
        if proxy is not None:
            out["proxyBuildSec"] = round(proxy, 1)
        ratio = _mean(data.get("analysisRatio", []))
        if ratio is not None:
            out["analysisTimeRatio"] = round(ratio, 3)
        for key in ("hwaccel", "hevcPlayable"):
            if isinstance(data.get(key), bool):
                out[key] = data[key]
        return out


def get_runtime_stats() -> RuntimeStats:
    return RuntimeStats(default_stats_path())


def record_proxy(encoder, seconds) -> None:
    try:
        get_runtime_stats().record_proxy(encoder, seconds)
    except Exception:
        log.debug("프록시 통계를 기록하지 못했다", exc_info=True)


def record_analysis(process_sec, game_sec, hwaccel) -> None:
    try:
        get_runtime_stats().record_analysis(process_sec=process_sec, game_sec=game_sec, hwaccel=hwaccel)
    except Exception:
        log.debug("분석 통계를 기록하지 못했다", exc_info=True)


def record_hevc(playable) -> None:
    try:
        get_runtime_stats().record_hevc(playable)
    except Exception:
        log.debug("HEVC 재생 가능 여부를 기록하지 못했다", exc_info=True)
