"""클립 자르기: 고른 구간만 남기고 나머지는 지운다.

`-c copy` 로 잘라 재인코딩이 없다(빠르고 화질 손실이 없다). 시작이 키프레임이 아니어도 MP4 편집 리스트로 시작 프레임이
정확히 맞는다(실측: 5.5초 지점 프레임과 픽셀 차이 0.0). 대신 시작 앞의 키프레임까지(최대 3초)는 화면에 안 보이는 채로 파일에 남는다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from lumia_briefing_room.config import ThumbnailConfig
from lumia_briefing_room.pipeline.clip import make_thumbnail
from lumia_briefing_room.pipeline.clip_assets import THUMBS_DIRNAME, resolve_thumbnail
from lumia_briefing_room.pipeline.clip_uid import (
    ARCHIVE_DIRNAME,
    UID_KEY,
    collect_uids,
    new_clip_uid,
    piece_uids,
    write_json_atomic,
)
from lumia_briefing_room.pipeline.retention import trash_clip
from lumia_briefing_room.procs import run_hidden

MIN_LENGTH_SEC = 1.0
END_TOLERANCE_SEC = 0.05


def validate_range(start: float, end: float, duration: float) -> None:
    if start < 0 or end <= start:
        raise ValueError("구간이 올바르지 않습니다")
    if end > duration + END_TOLERANCE_SEC:
        raise ValueError("끝 시각이 클립 길이를 넘을 수 없습니다")
    if end - start < MIN_LENGTH_SEC:
        raise ValueError(f"구간이 너무 짧습니다 (최소 {MIN_LENGTH_SEC:g}초)")


def validate_ranges(ranges: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    """구간을 시작 순으로 정렬해 돌려준다. 하나도 없거나 겹치면 ValueError."""
    if not ranges:
        raise ValueError("구간이 하나 이상 필요합니다")
    ordered = sorted(ranges)
    for start, end in ordered:
        validate_range(start, end, duration)
    for (_, prev_end), (next_start, _) in zip(ordered, ordered[1:]):
        if next_start < prev_end:
            raise ValueError("구간끼리 겹칠 수 없습니다")
    return ordered


def trim_clip(
    meta_path: Path, start: float, end: float, *, ffmpeg_path: Path, thumbnail: ThumbnailConfig
) -> dict:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    duration = float(meta["durationSec"])
    validate_range(start, end, duration)
    end = min(end, duration)

    mp4 = meta_path.with_suffix(".mp4")
    tmp = meta_path.with_suffix(".trim.mp4")
    cmd = [
        str(ffmpeg_path), "-hide_banner", "-v", "error", "-y",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(mp4),
        "-map", "0", "-c", "copy", str(tmp),
    ]
    try:
        run_hidden(cmd, check=True, capture_output=True)
        os.replace(tmp, mp4)
    finally:
        tmp.unlink(missing_ok=True)

    new_duration = round(end - start, 3)
    meta.setdefault("originalDurationSec", duration)
    meta["durationSec"] = new_duration
    meta["videoOffsetSec"] = round(float(meta.get("videoOffsetSec", 0.0)) + start, 3)
    meta["trimmed"] = True

    thumb = resolve_thumbnail(meta_path, meta)
    if thumb is not None:
        make_thumbnail(
            mp4, thumb, duration_sec=new_duration, offset_ratio=thumbnail.offset_ratio,
            width=thumbnail.width, ffmpeg_path=ffmpeg_path,
        )

    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def _free_piece_ids(meta_path: Path, trash_dir: Path, count: int) -> list[str]:
    ids: list[str] = []
    n = 1
    while len(ids) < count:
        candidate = f"{meta_path.stem}-p{n}"
        taken = any(
            (folder / f"{candidate}{suffix}").exists()
            for folder in (meta_path.parent, trash_dir)
            for suffix in (".json", ".mp4")
        )
        if not taken:
            ids.append(candidate)
        n += 1
    return ids


def split_clip(
    meta_path: Path,
    ranges: list[tuple[float, float]],
    *,
    trash_dir: Path,
    ffmpeg_path: Path,
    thumbnail: ThumbnailConfig,
) -> list[Path]:
    """구간마다 새 클립을 만들고 원본은 휴지통으로 옮긴다. 하나라도 실패하면 만든 조각을 지우고 원본은 그대로 둔다."""
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    duration = float(meta["durationSec"])
    ordered = validate_ranges(ranges, duration)
    src_mp4 = meta_path.with_suffix(".mp4")
    folder = meta_path.parent
    ids = _free_piece_ids(meta_path, trash_dir, len(ordered))
    parent_uid = meta.get(UID_KEY) or new_clip_uid()
    uids = piece_uids(parent_uid, collect_uids(folder, trash_dir, folder / ARCHIVE_DIRNAME), len(ordered))

    created: list[Path] = []
    try:
        for piece_id, piece_uid, (start, end) in zip(ids, uids, ordered):
            end = min(end, duration)
            piece_meta_path = folder / f"{piece_id}.json"
            piece_mp4 = piece_meta_path.with_suffix(".mp4")
            created.append(piece_mp4)
            cmd = [
                str(ffmpeg_path), "-hide_banner", "-v", "error", "-y",
                "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(src_mp4),
                "-map", "0", "-c", "copy", str(piece_mp4),
            ]
            run_hidden(cmd, check=True, capture_output=True)

            length = round(end - start, 3)
            piece = {k: v for k, v in meta.items() if k not in ("userLabel", "labelNote", "labelSource", "labelConflict", "labeledAt", "deletedAt")}
            piece.update(
                userLabel=None,
                durationSec=length,
                videoOffsetSec=round(float(meta.get("videoOffsetSec", 0.0)) + start, 3),
                trimmed=True,
                originalDurationSec=meta.get("originalDurationSec", duration),
                splitFrom=meta_path.stem,
                clipUid=piece_uid,
            )
            if meta.get("thumbnailPath"):
                thumb = folder / THUMBS_DIRNAME / f"{piece_id}.jpg"
                created.append(thumb)
                make_thumbnail(
                    piece_mp4, thumb, duration_sec=length, offset_ratio=thumbnail.offset_ratio,
                    width=thumbnail.width, ffmpeg_path=ffmpeg_path,
                )
                piece["thumbnailPath"] = f"{THUMBS_DIRNAME}/{piece_id}.jpg"
            created.append(piece_meta_path)
            piece_meta_path.write_text(json.dumps(piece, ensure_ascii=False, indent=2), encoding="utf-8")
        if not meta.get(UID_KEY):
            write_json_atomic(meta_path, meta | {UID_KEY: parent_uid})
        trash_clip(meta_path, trash_dir)
    except BaseException:
        for f in created:
            f.unlink(missing_ok=True)
        raise
    return [folder / f"{i}.json" for i in ids]
