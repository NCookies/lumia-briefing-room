from __future__ import annotations

import json
import queue
import re
import shutil
import subprocess
import threading
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from lumia_briefing_room import paths
from lumia_briefing_room.procs import popen_hidden, run_hidden

_PTS_TIME = re.compile(r"pts_time:(-?[0-9.]+)")
_PTS_WAIT_SEC = 30.0


def find_ffprobe(ffmpeg_path: Path | None = None) -> Path | None:
    """ffmpeg 와 같은 폴더의 ffprobe 를 먼저, 그다음 번들 폴더, 없으면 PATH 에서 찾는다."""
    folders = ([ffmpeg_path.parent] if ffmpeg_path is not None else []) + [paths.bundled_ffmpeg_dir()]
    for folder in folders:
        for name in ("ffprobe.exe", "ffprobe"):
            candidate = folder / name
            if candidate.exists():
                return candidate
    found = shutil.which("ffprobe")
    return Path(found) if found else None


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: float
    duration_sec: float
    codec: str


def _parse_rate(text: str) -> float:
    num, _, den = text.partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe_video(path: Path, *, ffprobe_path: Path) -> VideoInfo:
    if not path.exists():
        raise FileNotFoundError(path)
    proc = run_hidden(
        [
            str(ffprobe_path), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,codec_name:format=duration",
            "-of", "json", str(path),
        ],
        capture_output=True, check=True,
    )
    data = json.loads(proc.stdout.decode("utf-8"))
    stream = data["streams"][0]
    return VideoInfo(
        width=int(stream["width"]),
        height=int(stream["height"]),
        fps=_parse_rate(stream.get("r_frame_rate", "0/1")),
        duration_sec=float(data["format"]["duration"]),
        codec=stream.get("codec_name", ""),
    )


class VodFileSource:
    """영상 파일 하나(다시보기). 키프레임만 디코딩해 (원본 시각 초, 프레임) 으로 내준다.

    시각은 ffmpeg showinfo 가 찍는 키프레임 pts 그대로라 `ffmpeg -ss` 로 그 자리를 다시 자를 수 있다.
    프레임은 한 장씩 읽으므로 몇 시간짜리 영상도 메모리가 한 장 분량이다.
    """

    def __init__(
        self,
        path: Path,
        *,
        ffmpeg_path: Path,
        ffprobe_path: Path,
        start_sec: float = 0.0,
        end_sec: float | None = None,
        hwaccel: str | None = None,
    ) -> None:
        self.path = Path(path)
        self.info = probe_video(self.path, ffprobe_path=ffprobe_path)
        self.width = self.info.width
        self.height = self.info.height
        self._ffmpeg_path = ffmpeg_path
        self._start_sec = start_sec
        self._end_sec = end_sec
        self._hwaccel = hwaccel

    def gaps(self) -> list[tuple[float, float]]:
        return []

    def _command(self) -> list[str]:
        cmd = [str(self._ffmpeg_path), "-hide_banner", "-nostats", "-loglevel", "info"]
        if self._hwaccel:
            cmd += ["-hwaccel", self._hwaccel]
        cmd += ["-skip_frame", "nokey", "-copyts"]
        if self._start_sec > 0:
            cmd += ["-ss", f"{self._start_sec:.3f}"]
        if self._end_sec is not None:
            cmd += ["-to", f"{self._end_sec:.3f}"]
        cmd += [
            "-i", str(self.path), "-vf", "showinfo", "-fps_mode", "passthrough",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ]
        return cmd

    def frames(self) -> Iterator[tuple[float, np.ndarray]]:
        frame_bytes = self.width * self.height * 3
        proc = popen_hidden(
            self._command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        times: queue.Queue[float | None] = queue.Queue()
        tail: deque[str] = deque(maxlen=5)

        def drain_stderr() -> None:
            for raw in proc.stderr:
                line = raw.decode("utf-8", errors="replace").rstrip()
                match = _PTS_TIME.search(line)
                if match and "showinfo" in line:
                    times.put(float(match.group(1)))
                else:
                    tail.append(line)
            times.put(None)

        reader = threading.Thread(target=drain_stderr, daemon=True)
        reader.start()
        try:
            while True:
                data = proc.stdout.read(frame_bytes)
                if len(data) < frame_bytes:
                    break
                t = times.get(timeout=_PTS_WAIT_SEC)
                if t is None:
                    raise RuntimeError("프레임은 나왔는데 시각 정보가 없다")
                yield t, np.frombuffer(data, dtype=np.uint8).reshape(
                    self.height, self.width, 3
                )
            proc.wait()
            reader.join(timeout=5)
            if proc.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg 가 실패했다({proc.returncode}): {' | '.join(tail)}"
                )
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.stdout.close()
            proc.wait()
            reader.join(timeout=5)
