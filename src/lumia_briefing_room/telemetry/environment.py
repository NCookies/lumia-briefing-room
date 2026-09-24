"""오류 로그·진단에 붙이는 환경 정보(`Environment`). 값을 못 구하면 그 항목만 빠지고, 어떤 실패도 밖으로 내지 않는다.

아직 모으지 않는 항목(계약에는 있음): hwaccel, hevcPlayable, proxyEncoder, analysisTimeRatio, proxyBuildSec —
재생 가능 여부는 브라우저만 알고, 나머지는 앱이 값을 기록해 두지 않아서다.
"""

from __future__ import annotations

import ctypes
import locale
import logging
import math
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from lumia_briefing_room import __version__
from lumia_briefing_room.api.clips import scan_clips
from lumia_briefing_room.config import Config, discover_ffmpeg, resolve_paths
from lumia_briefing_room.recording_info import find_latest_session
from lumia_briefing_room.steam_paths import discover_recording_root, normalize_recording_root

log = logging.getLogger("lumia_briefing_room.telemetry.environment")


def read_fail_stats(cfg: Config) -> dict[str, int]:
    """판독이 비어 있는 클립 수. 게임 패치로 HUD 가 바뀌면 이 비율이 갑자기 오른다(조기 경보). 지금 있는 클립(휴지통 제외)만 센다."""
    resolved = resolve_paths(cfg.paths)
    stats = {"clips_total": 0, "no_match_result": 0, "no_my_character": 0, "no_region": 0, "no_game_day": 0,
             "no_match_kills": 0, "source_incomplete": 0}
    for root in (resolved.clips, resolved.vod_clips):
        for clip in scan_clips(root):
            meta = clip.meta
            stats["clips_total"] += 1
            stats["no_match_result"] += not meta.get("matchResult")
            stats["no_my_character"] += not meta.get("myCharacter")
            stats["no_region"] += not meta.get("region")
            stats["no_game_day"] += meta.get("gameDay") is None
            stats["no_match_kills"] += meta.get("matchKills") is None
            stats["source_incomplete"] += bool(meta.get("sourceIncomplete"))
    return {k: int(v) for k, v in stats.items()}


def _aspect_ratio(width: int, height: int) -> str:
    divisor = math.gcd(width, height) or 1
    return f"{width // divisor}:{height // divisor}"


def _windows_registry_string(key_path: str, value: str):
    import winreg

    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
        return winreg.QueryValueEx(key, value)[0]


def _cpu_model() -> str | None:
    try:
        if sys.platform == "win32":
            name = _windows_registry_string(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString")
            return " ".join(str(name).split())[:128] or None
    except Exception:
        pass
    return (platform.processor() or "")[:128] or None


def _gpu_name() -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg

        base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as root:
            for index in range(16):
                try:
                    with winreg.OpenKey(root, f"{index:04d}") as sub:
                        name = winreg.QueryValueEx(sub, "DriverDesc")[0]
                        if name and "Basic" not in str(name):
                            return str(name)[:128]
                except OSError:
                    continue
    except Exception:
        pass
    return None


def _memory_mb() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                        ("avail", ctypes.c_ulonglong), ("totalPage", ctypes.c_ulonglong),
                        ("availPage", ctypes.c_ulonglong), ("totalVirtual", ctypes.c_ulonglong),
                        ("availVirtual", ctypes.c_ulonglong), ("availExtended", ctypes.c_ulonglong)]

        status = Status()
        status.length = ctypes.sizeof(Status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return int(status.total // (1024 * 1024)) or None
    except Exception:
        return None


def _display_scale() -> float | None:
    if sys.platform != "win32":
        return None
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
        return round(dpi / 96, 2) if dpi else None
    except Exception:
        return None


def _ffmpeg_build() -> str | None:
    try:
        ffmpeg = discover_ffmpeg()
        if ffmpeg is None:
            return None
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run([str(ffmpeg), "-version"], capture_output=True, text=True, timeout=5, creationflags=flags)
        parts = out.stdout.splitlines()[0].split() if out.stdout else []
        return parts[2][:64] if len(parts) >= 3 and parts[0] == "ffmpeg" else None
    except Exception:
        return None


def _locale_name() -> str | None:
    try:
        return (locale.getlocale()[0] or os.environ.get("LANG") or "")[:32] or None
    except Exception:
        return None


def _timezone_name() -> str | None:
    try:
        return (datetime.now().astimezone().tzname() or "")[:64] or None
    except Exception:
        return None


def _recording(cfg: Config):
    root = normalize_recording_root(cfg.paths.steam_recording) or discover_recording_root()
    return find_latest_session(Path(root)) if root else None, root


def _buffer_minutes(cfg: Config, root) -> int | None:
    try:
        from lumia_briefing_room.pipeline.watcher import resolve_buffer_minutes

        return int(round(resolve_buffer_minutes(cfg, Path(root)))) if root else None
    except Exception:
        return None


def _safe(probe, *args):
    try:
        return probe(*args)
    except Exception:
        return None


def collect_environment(cfg: Config) -> dict:
    found = _safe(_recording, cfg)
    session, root = found if found else (None, None)
    values = {
        "appVersion": __version__,
        "os": platform.platform()[:128],
        "resolution": f"{session.width}x{session.height}" if session else None,
        "aspectRatio": _aspect_ratio(session.width, session.height) if session and session.width and session.height else None,
        "codec": ((session.codec or "")[:32] or None) if session else None,
        "displayScale": _safe(_display_scale),
        "cpuModel": _safe(_cpu_model),
        "cpuCores": os.cpu_count() or None,
        "gpuName": _safe(_gpu_name),
        "memoryMb": _safe(_memory_mb),
        "ffmpegBuild": _safe(_ffmpeg_build),
        "steamBufferMinutes": _safe(_buffer_minutes, cfg, root),
        "locale": _safe(_locale_name),
        "timezone": _safe(_timezone_name),
    }
    env = {k: v for k, v in values.items() if v is not None}
    stats = _safe(read_fail_stats, cfg)
    if stats is not None:
        env["readFailStats"] = stats
    return env
