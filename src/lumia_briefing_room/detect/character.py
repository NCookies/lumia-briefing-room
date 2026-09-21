from __future__ import annotations

import json
import re
from pathlib import Path

import cv2
import numpy as np

from lumia_briefing_room.detect.ocr import TextReader

MIN_PREFIX_LEN = 4
MIN_TEXT_LEN = 3
MIN_SCORE = 0.8
SCALE = 2
_NON_LETTERS = re.compile(r"[^A-Z]")
_CHARACTERS_PATH = Path(__file__).resolve().parents[3] / "data" / "characters.json"


def load_characters(path: Path = _CHARACTERS_PATH) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {english.upper(): korean for english, korean in data.items()}


def clean_character_text(text: str) -> str | None:
    cleaned = _NON_LETTERS.sub("", text.upper())
    return cleaned if len(cleaned) >= MIN_TEXT_LEN else None


def resolve_character(raw: str | None, table: dict[str, str]) -> str | None:
    """캐릭터 일러스트에 가려 잘린 영문 이름(`MARKU`)을 이름표의 유일한 접두어로 되살린다. 모호하면 포기한다."""
    if not raw:
        return None
    if raw in table:
        return table[raw]
    if len(raw) < MIN_PREFIX_LEN:
        return None
    matches = {korean for english, korean in table.items() if english.startswith(raw)}
    return matches.pop() if len(matches) == 1 else None


def enhance_vertical_text(rgb: np.ndarray) -> np.ndarray:
    """결과 화면 오른쪽의 세로 영문 이름은 검은 바탕에 아주 어두운 회색이라 대비를 늘리고 눕혀야 OCR 이 읽는다."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    lo, hi = np.percentile(gray, 2), np.percentile(gray, 60)
    stretched = np.clip((gray - lo) / (hi - lo + 1e-6), 0.0, 1.0)
    big = cv2.resize((stretched * 255).astype(np.uint8), None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)
    return cv2.rotate(big, cv2.ROTATE_90_COUNTERCLOCKWISE)


def read_character_raw(crop: np.ndarray, reader: TextReader) -> str | None:
    image = np.stack([enhance_vertical_text(crop)] * 3, axis=-1)
    best: tuple[float, str] | None = None
    for lang in ("ch", "korean"):
        for line in reader.read(image, lang=lang):
            text = clean_character_text(line.text)
            if text and line.score >= MIN_SCORE and (best is None or line.score > best[0]):
                best = (line.score, text)
    return best[1] if best else None
