from __future__ import annotations

import re
from dataclasses import dataclass, field

import cv2
import numpy as np

from lumia_briefing_room.detect.character import load_characters, read_character_raw, resolve_character
from lumia_briefing_room.detect.ocr import TextLine, TextReader
from lumia_briefing_room.profiles.models import ResolutionProfile
from lumia_briefing_room.video.frames import crop_roi

PLACEMENT_RE = re.compile(r"^(\d{1,2})\s*/\s*(\d{1,2})$")
CHIP_THRESHOLD = 200
NICKNAME_SCALE = 3
NICKNAME_MARGIN = 8
_BAR_PREFIX = re.compile(r"^[\s|{}\[\]!Il]+(?=\S)")
_HANGUL = re.compile(r"[가-힣]")
MIN_OUTCOME_HANGUL = 2
MIN_OUTCOME_SCORE = 0.8
MIN_STAT_SCORE = 0.6
STAT_COLUMN_TOLERANCE = 60
STAT_ROW_MAX_GAP = 90
STAT_LABELS = {"TK": "tk", "K": "kills", "D": "deaths", "A": "assists"}
LANGS = ("korean", "ch")


@dataclass(frozen=True)
class ResultScreen:
    """SPEC §2.13: 경기 종료 결과 화면(`4/7 실험 종료`)에서 읽은 값."""

    placement: int
    total: int
    match_type: str
    match_label: str
    outcome: str | None
    nickname: str | None
    character: str | None = None
    character_raw: str | None = None
    stats: dict | None = None
    image: np.ndarray | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class PanelParse:
    placement: int
    total: int
    outcome: str | None
    nickname_line: TextLine | None
    stats: dict | None = None


def clean_nickname(text: str) -> str:
    """닉네임 왼쪽의 파란 막대가 `|`, `{` 등으로 읽히는 것을 걷어낸다."""
    return _BAR_PREFIX.sub("", text.strip()).strip()


def _is_outcome(line: TextLine) -> bool:
    return (
        line.score >= MIN_OUTCOME_SCORE
        and len(_HANGUL.findall(line.text)) >= MIN_OUTCOME_HANGUL
        and not _BAR_PREFIX.match(line.text)
    )


def parse_stats(lines: list[TextLine]) -> dict:
    """`TK K D A` 라벨 바로 아래 같은 열의 숫자를 읽는다. 자릿수가 달라도 열 위치(x)로 짝을 짓는다."""
    stats: dict = {name: None for name in STAT_LABELS.values()}
    labels = {l.text.strip(): l for l in lines if l.text.strip() in STAT_LABELS}
    if len(labels) < len(STAT_LABELS):
        return stats
    for text, label in labels.items():
        candidates = [
            l for l in lines
            if l.text.strip().isdigit()
            and l.score >= MIN_STAT_SCORE
            and 0 < l.y - label.y <= STAT_ROW_MAX_GAP
            and abs(l.x - label.x) <= STAT_COLUMN_TOLERANCE
        ]
        if candidates:
            nearest = min(candidates, key=lambda l: (l.y - label.y, abs(l.x - label.x)))
            stats[STAT_LABELS[text]] = int(nearest.text.strip())
    return stats


def parse_panel(lines: list[TextLine]) -> PanelParse | None:
    """결과 화면 좌측 패널의 OCR 줄들에서 순위·결과 문구·닉네임 줄을 골라낸다.

    글자 위치가 아니라 순서로 찾는다: 순위(`N/M`) 뒤 막대(`|`)로 시작하는 줄이 닉네임이고, 그 바로 위 한글 줄이 결과 문구다.
    모드 칩(`랭크 대전`)이 패널 OCR 에 읽히는 프레임이 있어 문구는 닉네임에 가장 가까운 줄로 잡는다.
    """
    ordered = sorted(lines, key=lambda l: (l.y, l.x))
    for i, ln in enumerate(ordered):
        m = PLACEMENT_RE.match(ln.text.strip())
        if not m:
            continue
        placement, total = int(m.group(1)), int(m.group(2))
        if not 1 <= placement <= total:
            return None

        rest = ordered[i + 1 :]
        nickname_line = next((l for l in rest if _BAR_PREFIX.match(l.text)), None)
        above = rest[: rest.index(nickname_line)] if nickname_line else rest
        candidates = [l for l in above if _is_outcome(l)]
        outcome_line = candidates[-1] if nickname_line else (candidates[0] if candidates else None)
        return PanelParse(
            placement, total, outcome_line.text.strip() if outcome_line else None, nickname_line, parse_stats(ordered)
        )
    return None


def _binarize_dark_on_light(rgb: np.ndarray, threshold: int = CHIP_THRESHOLD) -> np.ndarray:
    """밝은 글자만 남겨 흰 바탕에 검은 글자로 뒤집고 3배 키운다. 파란 알약 위 흰 글자를 OCR 이 읽게 한다."""
    ink = rgb.min(axis=-1) > threshold
    gray = np.where(ink, 0, 255).astype(np.uint8)
    big = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    padded = cv2.copyMakeBorder(big, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return np.stack([padded] * 3, axis=-1)


def read_nickname(panel: np.ndarray, line: TextLine, reader: TextReader) -> str | None:
    """닉네임 줄만 잘라 키운 뒤 한글/한자·일본어 모델을 둘 다 돌려 점수가 높은 쪽을 쓴다."""
    y0 = max(line.y - NICKNAME_MARGIN, 0)
    y1 = min(line.y + line.h + NICKNAME_MARGIN, panel.shape[0])
    crop = cv2.resize(panel[y0:y1], None, fx=NICKNAME_SCALE, fy=NICKNAME_SCALE, interpolation=cv2.INTER_CUBIC)

    best: tuple[float, str] | None = None
    for lang in LANGS:
        for read in reader.read(crop, lang=lang):
            text = clean_nickname(read.text)
            if text and (best is None or read.score > best[0]):
                best = (read.score, text)
    return best[1] if best else clean_nickname(line.text) or None


def _match_type(chip_text: str) -> str:
    if not chip_text:
        return "unknown"
    return "rank" if "랭크" in chip_text else "normal"


def read_result_screen(
    frame: np.ndarray,
    profile: ResolutionProfile,
    reader: TextReader,
    characters: dict[str, str] | None = None,
) -> ResultScreen | None:
    panel = crop_roi(frame, profile.rois["result_panel"])
    parsed = parse_panel(reader.read(panel))
    if parsed is None:
        return None

    chip_lines = reader.read(_binarize_dark_on_light(crop_roi(frame, profile.rois["result_chip"])))
    chip_text = " ".join(l.text.strip() for l in chip_lines if l.score >= 0.8)
    nickname = read_nickname(panel, parsed.nickname_line, reader) if parsed.nickname_line else None
    character_raw = read_character_raw(crop_roi(frame, profile.rois["result_character"]), reader)
    table = characters if characters is not None else load_characters()

    return ResultScreen(
        placement=parsed.placement,
        total=parsed.total,
        match_type=_match_type(chip_text),
        match_label=chip_text,
        outcome=parsed.outcome,
        nickname=nickname,
        character=resolve_character(character_raw, table),
        character_raw=character_raw,
        stats=parsed.stats,
        image=frame,
    )
