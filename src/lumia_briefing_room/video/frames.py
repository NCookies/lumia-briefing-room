from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from lumia_briefing_room.profiles.models import Roi
from lumia_briefing_room.video.session import RecordingSession
from lumia_briefing_room.procs import run_hidden


def reshape_raw_frames(raw: bytes, *, width: int, height: int) -> np.ndarray:
    """ffmpeg rawvideo(rgb24) 출력을 (N, H, W, 3) 배열로 되돌린다."""
    frame_bytes = width * height * 3
    if len(raw) % frame_bytes != 0:
        raise ValueError(
            f"raw 크기({len(raw)})가 프레임 크기({frame_bytes})의 배수가 아니다"
        )
    count = len(raw) // frame_bytes
    return np.frombuffer(raw, dtype=np.uint8).reshape(count, height, width, 3)


def crop_roi(frame: np.ndarray, roi: Roi) -> np.ndarray:
    return frame[roi.y0 : roi.y1, roi.x0 : roi.x1]


def _existing_chunk_paths(
    session: RecordingSession, stream: int, segment_numbers: list[int]
) -> list[tuple[int, Path]]:
    """존재하는 조각만 (번호, 경로) 로, 번호 오름차순으로 반환한다.

    research §1.6: "폴더가 있으니 조각도 있다"는 가정은 틀린다 — 존재 확인은 필수.
    """
    result = []
    for n in sorted(segment_numbers):
        path = session.directory / f"chunk-stream{stream}-{n:05d}.m4s"
        if path.exists():
            result.append((n, path))
    return result


def _contiguous_runs(
    items: list[tuple[int, Path]],
) -> list[list[tuple[int, Path]]]:
    """번호가 연속인 항목끼리 묶는다.

    한 개의 fMP4 스트림 안에 번호가 끊긴 조각을 그대로 이어붙이면 프래그먼트의
    바이트 오프셋 참조가 깨진다(실측: gap 있는 병합에서 NAL 유닛 크기가 쓰레기값으로
    깨져 디코딩이 중단됨). 그래서 연속 구간마다 별도로 병합·디코딩한다.
    """
    if not items:
        return []
    runs: list[list[tuple[int, Path]]] = [[items[0]]]
    for item in items[1:]:
        if item[0] == runs[-1][-1][0] + 1:
            runs[-1].append(item)
        else:
            runs.append([item])
    return runs


def _decode_run(
    init_bytes: bytes,
    run: list[tuple[int, Path]],
    *,
    width: int,
    height: int,
    ffmpeg_path: Path,
    hwaccel: str | None,
) -> Iterator[tuple[int, np.ndarray]]:
    with tempfile.TemporaryDirectory(prefix="lumia_frames_") as tmp_dir:
        merged_path = Path(tmp_dir) / "merged.mp4"
        with open(merged_path, "wb") as out:
            out.write(init_bytes)
            for _, chunk_path in run:
                out.write(chunk_path.read_bytes())

        cmd = [str(ffmpeg_path), "-hide_banner", "-v", "error"]
        if hwaccel:
            cmd += ["-hwaccel", hwaccel]
        cmd += [
            "-skip_frame",
            "nokey",
            "-i",
            str(merged_path),
            "-fps_mode",
            "passthrough",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ]
        proc = run_hidden(cmd, capture_output=True, check=True)

    frames = reshape_raw_frames(proc.stdout, width=width, height=height)

    if frames.shape[0] != len(run):
        raise RuntimeError(
            f"키프레임 개수({frames.shape[0]})가 세그먼트 개수({len(run)})와 다르다"
        )

    for (segment_number, _), frame in zip(run, frames):
        yield segment_number, frame


def largest_contiguous_run(items: list[tuple[int, Path]]) -> list[tuple[int, Path]]:
    runs = _contiguous_runs(items)
    return max(runs, key=len) if runs else []


def write_merged_segment_file(
    session: RecordingSession, stream: int, segment_numbers: list[int], out_path: Path
) -> list[int]:
    """존재하는 세그먼트 중 가장 긴 연속 구간만 이어붙여 유효한 fMP4 파일을 만든다.

    gap 을 넘어 이어붙이면 프래그먼트 바이트 오프셋이 깨질 수 있어(§ 위 주석)
    가장 긴 연속 구간만 쓴다. 반환값은 실제로 쓰인 세그먼트 번호(오름차순)다.
    """
    existing = _existing_chunk_paths(session, stream, segment_numbers)
    run = largest_contiguous_run(existing)
    if not run:
        return []

    init_bytes = (session.directory / f"init-stream{stream}.m4s").read_bytes()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as out:
        out.write(init_bytes)
        for _, chunk_path in run:
            out.write(chunk_path.read_bytes())
    return [n for n, _ in run]


def extract_keyframe_frames(
    session: RecordingSession,
    *,
    stream: int,
    segment_numbers: list[int],
    ffmpeg_path: Path,
    hwaccel: str | None = None,
) -> Iterator[tuple[int, np.ndarray]]:
    """세그먼트별 키프레임 1장(풀해상도 rgb24)을 (세그먼트 번호, ndarray) 로 방출한다.

    research.md §2.4, §2.2: 세그먼트마다 정확히 키프레임 1개가 3.000초 간격으로 있다.
    존재하지 않는 세그먼트는 건너뛴다 — 링버퍼가 이미 지웠을 수 있다.
    """
    existing = _existing_chunk_paths(session, stream, segment_numbers)
    if not existing:
        return

    init_bytes = (session.directory / f"init-stream{stream}.m4s").read_bytes()

    for run in _contiguous_runs(existing):
        yield from _decode_run(
            init_bytes,
            run,
            width=session.width,
            height=session.height,
            ffmpeg_path=ffmpeg_path,
            hwaccel=hwaccel,
        )
