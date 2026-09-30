from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import cv2
import numpy as np

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
MIN_STATS_WITHOUT_PLACEMENT = 3
STAT_COLUMN_TOLERANCE = 60
STAT_ROW_MAX_GAP = 90
STAT_LABELS = {"TK": "tk", "K": "kills", "D": "deaths", "A": "assists"}
LANGS = ("korean", "ch")


@dataclass(frozen=True)
class ResultScreen:
    """SPEC §2.13: 경기 종료 결과 화면(`4/7 실험 종료`)에서 읽은 값."""

    placement: int | None
    total: int | None
    match_type: str
    match_label: str
    outcome: str | None
    nickname: str | None
    stats: dict | None = None
    image: np.ndarray | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class PanelParse:
    placement: int | None
    total: int | None
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
            # 열(x)이 먼저다 - 위 docstring대로. 행 간격(y)을 먼저 보면 다른 열의 값이
            # 우연히 한 행 더 가까울 때 잘못 짝지어진다(코발트 팀원 카드처럼 열 간격이
            # 좁으면 실제로 벌어진다, plan.md §10 C3 실측).
            nearest = min(candidates, key=lambda l: (abs(l.x - label.x), l.y - label.y))
            stats[STAT_LABELS[text]] = int(nearest.text.strip())
    return stats


def _parse_after(placement: int | None, total: int | None, rest: list[TextLine], ordered: list[TextLine]) -> PanelParse:
    nickname_line = next((l for l in rest if _BAR_PREFIX.match(l.text)), None)
    above = rest[: rest.index(nickname_line)] if nickname_line else rest
    candidates = [l for l in above if _is_outcome(l)]
    outcome_line = (candidates[-1] if nickname_line else candidates[0]) if candidates else None
    return PanelParse(
        placement, total, outcome_line.text.strip() if outcome_line else None, nickname_line, parse_stats(ordered)
    )


def _parse_without_placement(ordered: list[TextLine]) -> PanelParse | None:
    """순위(`N/M`)가 안 읽힌 결과 화면. 닉네임 줄과 스탯이 함께 읽힐 때만 결과 화면으로 본다(순위 없이 넓게 받으면 오탐이 는다)."""
    parsed = _parse_after(None, None, ordered, ordered)
    read_stats = sum(v is not None for v in (parsed.stats or {}).values())
    if parsed.nickname_line is None or read_stats < MIN_STATS_WITHOUT_PLACEMENT:
        return None
    return parsed


def parse_panel(lines: list[TextLine]) -> PanelParse | None:
    """결과 화면 좌측 패널의 OCR 줄들에서 순위·결과 문구·닉네임 줄을 골라낸다.

    글자 위치가 아니라 순서로 찾는다: 순위(`N/M`) 뒤 막대(`|`)로 시작하는 줄이 닉네임이고, 그 바로 위 한글 줄이 결과 문구다.
    모드 칩(`랭크 대전`)이 패널 OCR 에 읽히는 프레임이 있어 문구는 닉네임에 가장 가까운 줄로 잡는다.
    순위가 안 읽히면(글꼴의 일부 숫자를 OCR 이 못 읽는다) 순위만 비우고 나머지를 돌려준다.
    """
    ordered = sorted(lines, key=lambda l: (l.y, l.x))
    for i, ln in enumerate(ordered):
        m = PLACEMENT_RE.match(ln.text.strip())
        if not m:
            continue
        placement, total = int(m.group(1)), int(m.group(2))
        if not 1 <= placement <= total:
            break
        return _parse_after(placement, total, ordered[i + 1 :], ordered)
    return _parse_without_placement(ordered)


def _binarize_dark_on_light(rgb: np.ndarray, threshold: int = CHIP_THRESHOLD) -> np.ndarray:
    """밝은 글자만 남겨 흰 바탕에 검은 글자로 뒤집고 3배 키운다. 파란 알약 위 흰 글자를 OCR 이 읽게 한다."""
    ink = rgb.min(axis=-1) > threshold
    gray = np.where(ink, 0, 255).astype(np.uint8)
    big = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    padded = cv2.copyMakeBorder(big, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return np.stack([padded] * 3, axis=-1)


def _upscale(rgb: np.ndarray) -> np.ndarray:
    return cv2.resize(rgb, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)


def read_chip(chip: np.ndarray, reader: TextReader) -> str:
    """모드 칩 글자. 그냥 3배 확대가 먼저(실측: 이진화보다 훨씬 잘 읽힌다), 못 읽으면 이진화(파란 랭크 칩용)."""
    for prepare in (_upscale, _binarize_dark_on_light):
        lines = reader.read(prepare(chip))
        text = " ".join(l.text.strip() for l in lines if l.score >= 0.8)
        if text:
            return text
    return ""


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
) -> ResultScreen | None:
    panel = crop_roi(frame, profile.rois["result_panel"])
    parsed = parse_panel(reader.read(panel))
    if parsed is None:
        return None

    chip_text = read_chip(crop_roi(frame, profile.rois["result_chip"]), reader)
    nickname = read_nickname(panel, parsed.nickname_line, reader) if parsed.nickname_line else None

    return ResultScreen(
        placement=parsed.placement,
        total=parsed.total,
        match_type=_match_type(chip_text),
        match_label=chip_text,
        outcome=parsed.outcome,
        nickname=nickname,
        stats=parsed.stats,
        image=frame,
    )


def _majority(values: list):
    """None 을 뺀 값 중 가장 많은 것. 동률이면 먼저 나온 쪽."""
    known = [v for v in values if v is not None]
    return Counter(known).most_common(1)[0][0] if known else None


def _filled(result: ResultScreen) -> int:
    fields = [result.placement, result.outcome, result.nickname, result.match_type != "unknown" or None]
    return sum(f is not None for f in fields) + sum(v is not None for v in (result.stats or {}).values())


def merge_results(results: list[ResultScreen]) -> ResultScreen | None:
    """같은 결과 화면을 여러 장 읽은 값을 항목별 다수결로 합친다. OCR 이 장마다 다른 곳을 틀리기 때문이다.

    못 읽은 값(None, unknown)은 표에 넣지 않는다. 결과표 이미지는 가장 많은 항목이 읽힌 장이다.
    """
    if not results:
        return None
    placement, total = _majority([(r.placement, r.total) for r in results if r.placement is not None]) or (None, None)
    match_type = _majority([r.match_type for r in results if r.match_type != "unknown"]) or "unknown"
    stat_keys = dict.fromkeys(k for r in results for k in (r.stats or {}))
    stats = {k: _majority([(r.stats or {}).get(k) for r in results]) for k in stat_keys} if stat_keys else None
    return ResultScreen(
        placement=placement,
        total=total,
        match_type=match_type,
        match_label=_majority([r.match_label for r in results if r.match_type == match_type and r.match_label]) or "",
        outcome=_majority([r.outcome for r in results]),
        nickname=_majority([r.nickname for r in results]),
        stats=stats,
        image=max(results, key=_filled).image,
    )
