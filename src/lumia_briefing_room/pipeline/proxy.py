"""HEVC 를 못 재생하는 PC 를 위한 H.264 재생용 프록시. (plan-deploy.md D4)

원본 클립은 그대로 두고 `<클립 폴더>/.proxy/<클립ID>.mp4` 에 재생용 사본을 만든다. 재생하려고 할 때 처음 만든다.
"""

import logging
import os
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from lumia_briefing_room.api.clips import scan_clips
from lumia_briefing_room.procs import popen_hidden, run_hidden
from lumia_briefing_room.telemetry.runtime_stats import record_proxy

log = logging.getLogger("lumia_briefing_room.proxy")

PREFERRED_ENCODERS = ("h264_mf", "libx264")
BASE_BITRATE_KBPS = 8000
BASE_HEIGHT = 1080
MIN_BITRATE_KBPS = 1500
GOP_FRAMES = 60
_ENCODER_LINE = re.compile(r"^\s*V\S*\s+(\S+)\s")
_encoder_cache: dict[str, set[str]] = {}


class ProxyError(Exception):
    pass


def proxy_dir(clips_dir: Path) -> Path:
    return clips_dir / ".proxy"


def proxy_path(clips_dir: Path, clip_id: str) -> Path:
    return proxy_dir(clips_dir) / f"{clip_id}.mp4"


def is_proxy_fresh(proxy: Path, source: Path) -> bool:
    """자르기로 원본이 바뀌면(mtime 이 더 새로우면) 옛 프록시는 못 쓴다."""
    try:
        return proxy.stat().st_size > 0 and proxy.stat().st_mtime >= source.stat().st_mtime
    except OSError:
        return False


def proxy_bitrate_kbps(height: int) -> int:
    return max(MIN_BITRATE_KBPS, round(BASE_BITRATE_KBPS * (height / BASE_HEIGHT) ** 2))


def parse_encoders(text: str) -> set[str]:
    return {m.group(1) for line in text.splitlines() if (m := _ENCODER_LINE.match(line))}


def list_encoders(ffmpeg: Path) -> set[str]:
    key = str(ffmpeg)
    if key not in _encoder_cache:
        out = run_hidden([key, "-hide_banner", "-encoders"], capture_output=True, text=True, check=True).stdout
        _encoder_cache[key] = parse_encoders(out)
    return _encoder_cache[key]


def encoder_plan(available: set[str]) -> list[str]:
    return [name for name in PREFERRED_ENCODERS if name in available]


def build_proxy_command(ffmpeg: Path, src: Path, out: Path, *, encoder: str, height: int, crf: int) -> list[str]:
    cmd = [
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1", "-y",
        "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", f"scale=-2:min({height}\\,ih),format=yuv420p",
        "-c:v", encoder,
    ]
    if encoder == "libx264":
        cmd += ["-preset", "veryfast", "-crf", str(crf)]
    else:
        cmd += ["-b:v", f"{proxy_bitrate_kbps(height)}k"]
    cmd += ["-g", str(GOP_FRAMES), "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
    return cmd


def _run_encode(cmd: list[str], duration_sec: float, on_progress: Callable[[float], None] | None) -> None:
    proc = popen_hidden(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    tail: list[str] = []
    try:
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    seconds = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    continue
                if on_progress and duration_sec > 0:
                    on_progress(max(0.0, min(1.0, seconds / duration_sec)))
            elif "=" not in line and line:
                tail.append(line)
        code = proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
    if code != 0:
        raise ProxyError(" | ".join(tail[-3:]) or f"ffmpeg 종료 코드 {code}")
    if on_progress:
        on_progress(1.0)


def create_proxy(
    ffmpeg: Path,
    src: Path,
    out: Path,
    *,
    height: int,
    crf: int,
    duration_sec: float,
    on_progress: Callable[[float], None] | None = None,
) -> str:
    """가능한 인코더를 차례로 시도해 프록시를 만들고, 쓴 인코더 이름을 돌려준다."""
    plan = encoder_plan(list_encoders(ffmpeg))
    if not plan:
        raise ProxyError("이 ffmpeg에 H.264 인코더(h264_mf, libx264)가 없습니다")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.stem}.tmp.mp4")
    errors = []
    try:
        for encoder in plan:
            tmp.unlink(missing_ok=True)
            cmd = build_proxy_command(ffmpeg, src, tmp, encoder=encoder, height=height, crf=crf)
            started = time.monotonic()
            try:
                _run_encode(cmd, duration_sec, on_progress)
            except ProxyError as exc:
                log.warning("프록시 인코더 %s 실패: %s", encoder, exc)
                errors.append(f"{encoder}: {exc}")
                continue
            os.replace(tmp, out)
            record_proxy(encoder, time.monotonic() - started)
            return encoder
        raise ProxyError("; ".join(errors))
    finally:
        tmp.unlink(missing_ok=True)


def remove_proxy(clips_dir: Path, clip_id: str) -> None:
    proxy_path(clips_dir, clip_id).unlink(missing_ok=True)


def remove_orphan_proxies(clips_dir: Path, trash_dir: Path) -> list[Path]:
    """클립(휴지통 포함)이 더는 없는 프록시와 만들다 만 임시 파일을 지운다."""
    directory = proxy_dir(clips_dir)
    if not directory.exists():
        return []
    alive = {c.id for root in (clips_dir, trash_dir) for c in scan_clips(root)}
    removed = []
    for path in directory.glob("*.mp4"):
        if path.name.split(".", 1)[0] not in alive:
            path.unlink(missing_ok=True)
            removed.append(path)
    return removed
