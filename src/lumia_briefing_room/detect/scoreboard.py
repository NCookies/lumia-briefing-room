from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

import cv2
import numpy as np

from lumia_briefing_room.detect.ocr import TextLine, TextReader
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.frames import crop_roi

PLACEMENT_RE = re.compile(r"^\d{1,2}\s*위$")
RANK_RE = re.compile(r"^\d{1,2}$")
_NON_HANGUL = re.compile(r"[^가-힣]")

ROW_GAP = 60
SAME_LINE_TOLERANCE = 12
RANK_MATCH_TOLERANCE = 45
CHARACTER_CUTOFF = 0.6
NICKNAME_CUTOFF = 0.75
MIN_LINE_SCORE = 0.5

# (밝기 하한, 이득, 배율): 밝은 글자만 강조해 흐린 부제(캐릭터 이름)를 살린다. 마지막은 원본 2배.
PASSES: tuple[tuple[int | None, float | None, int], ...] = ((90, 2.0, 3), (90, 3.0, 2), (60, 2.0, 2), (None, None, 2))
RANK_SCALE = 2


@dataclass(frozen=True)
class BoardRow:
    rank: int | None
    nickname: str
    character: str | None
    y: int = field(default=0, compare=False)


def snap_character(text: str, roster: list[str]) -> str | None:
    """OCR 로 읽은 부제를 캐릭터 이름표에 맞춘다. 표에 없는 글자(닉네임, 깨진 글자)는 None 이다."""
    cleaned = _NON_HANGUL.sub("", text)
    if len(cleaned) < 2:
        return None
    match = difflib.get_close_matches(cleaned, roster, n=1, cutoff=CHARACTER_CUTOFF)
    return match[0] if match else None


def merge_passes(passes: list[list[TextLine]], roster: list[str]) -> list[TextLine]:
    """여러 전처리로 읽은 줄들을 같은 높이끼리 묶어 하나씩만 남긴다. 캐릭터 이름표에 맞는 읽기를 우선한다."""
    lines = sorted((l for p in passes for l in p), key=lambda l: l.y)
    clusters: list[list[TextLine]] = []
    for l in lines:
        if clusters and l.y - clusters[-1][0].y <= SAME_LINE_TOLERANCE:
            clusters[-1].append(l)
        else:
            clusters.append([l])

    merged = []
    for cluster in clusters:
        known = [l for l in cluster if snap_character(l.text, roster)]
        merged.append(max(known or cluster, key=lambda l: l.score))
    return merged


def _is_text_line(line: TextLine) -> bool:
    """닉네임 옆의 레벨 숫자(`19`)나 한 글자 잡음은 행의 글자로 치지 않는다."""
    text = line.text.strip()
    return len(text) >= 2 and not text.isdigit()


def group_rows(lines: list[TextLine], roster: list[str]) -> list[BoardRow]:
    """행마다 첫 줄이 닉네임, 그 바로 아래(ROW_GAP 이내) 줄이 캐릭터 이름 부제다."""
    rows: list[BoardRow] = []
    ordered = sorted((l for l in lines if _is_text_line(l)), key=lambda l: l.y)
    i = 0
    while i < len(ordered):
        nick = ordered[i]
        character = None
        if i + 1 < len(ordered) and ordered[i + 1].y - nick.y <= ROW_GAP:
            character = snap_character(ordered[i + 1].text, roster)
            i += 1
        rows.append(BoardRow(rank=None, nickname=nick.text.strip(), character=character, y=nick.y))
        i += 1
    return rows


def _enhance(rgb: np.ndarray, lo: int | None, gain: float | None, scale: int) -> np.ndarray:
    if lo is None:
        return cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    bright = np.clip((rgb.astype(np.int16).min(axis=-1) - lo) * gain, 0, 255).astype(np.uint8)
    big = cv2.resize(bright, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return np.stack([big] * 3, axis=-1)


def _to_frame(lines: list[TextLine], y0: int, scale: int) -> list[TextLine]:
    return [
        TextLine(text=l.text, score=l.score, x=l.x // scale, y=y0 + l.y // scale, h=l.h // scale)
        for l in lines
        if l.text.strip() and l.score >= MIN_LINE_SCORE
    ]


def read_scoreboard(
    frame: np.ndarray, profile: ResolutionProfile, reader: TextReader, roster: list[str]
) -> list[BoardRow] | None:
    """결과 후 `순위표` 탭에서 플레이어마다 (순위, 닉네임, 캐릭터 이름) 을 읽는다. 순위표 화면이 아니면 None."""
    panel = reader.read(crop_roi(frame, profile.rois["scoreboard_panel"]))
    if not any(PLACEMENT_RE.match(l.text.strip()) for l in panel):
        return None

    names_roi = profile.rois["scoreboard_names"]
    names_crop = crop_roi(frame, names_roi)
    passes = [
        _to_frame(reader.read(_enhance(names_crop, lo, gain, scale)), names_roi.y0, scale)
        for lo, gain, scale in PASSES
    ]
    rows = group_rows(merge_passes(passes, roster), roster)
    if not rows:
        return None

    ranks_roi = profile.rois["scoreboard_ranks"]
    rank_lines = _to_frame(
        reader.read(_enhance(crop_roi(frame, ranks_roi), None, None, RANK_SCALE)), ranks_roi.y0, RANK_SCALE
    )
    rank_lines = [l for l in rank_lines if RANK_RE.match(l.text.strip())]

    result = []
    for row in rows:
        near = [l for l in rank_lines if abs(l.y - row.y) <= RANK_MATCH_TOLERANCE]
        rank = int(min(near, key=lambda l: abs(l.y - row.y)).text) if near else None
        result.append(BoardRow(rank=rank, nickname=row.nickname, character=row.character, y=row.y))
    return result


def find_team(rows: list[BoardRow], my_nickname: str | None) -> tuple[BoardRow, list[BoardRow]] | None:
    """내 닉네임 행을 찾고, 같은 순위의 다른 행들을 팀원으로 돌려준다. 내 행이나 순위를 모르면 None."""
    if not my_nickname or not rows:
        return None
    target = my_nickname.strip().casefold()
    scored = [(difflib.SequenceMatcher(None, r.nickname.casefold(), target).ratio(), r) for r in rows]
    ratio, me = max(scored, key=lambda pair: pair[0])
    if ratio < NICKNAME_CUTOFF or me.rank is None:
        return None
    return me, [r for r in rows if r is not me and r.rank == me.rank]
