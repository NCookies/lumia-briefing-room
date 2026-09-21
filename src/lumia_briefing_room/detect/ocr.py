from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TextLine:
    text: str
    score: float
    x: int
    y: int
    h: int


class TextReader(Protocol):
    def read(self, rgb: np.ndarray, *, lang: str = "korean") -> list[TextLine]: ...


class OcrReader:
    """RapidOCR(ONNX) 로 화면 글자를 읽는다. 엔진과 모델은 처음 쓸 때 불러온다.

    lang: `korean` 은 한글+영문, `ch` 는 한자·일본어(가나)·영문. 닉네임은 두 언어가 섞여 있을 수 있어 호출 쪽이 둘 다 돌려 점수가 높은 쪽을 쓴다.
    """

    def __init__(self) -> None:
        self._engines: dict[str, object] = {}

    def _engine(self, lang: str):
        if lang not in self._engines:
            from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

            rec = {"korean": LangRec.KOREAN, "ch": LangRec.CH}[lang]
            self._engines[lang] = RapidOCR(
                params={
                    "Rec.lang_type": rec,
                    "Rec.ocr_version": OCRVersion.PPOCRV5,
                    "Rec.model_type": ModelType.MOBILE,
                    "Global.log_level": "error",
                }
            )
        return self._engines[lang]

    def read(self, rgb: np.ndarray, *, lang: str = "korean") -> list[TextLine]:
        result = self._engine(lang)(np.ascontiguousarray(rgb))
        if result.txts is None:
            return []
        lines = []
        for box, text, score in zip(result.boxes, result.txts, result.scores):
            ys = [p[1] for p in box]
            lines.append(
                TextLine(text=text, score=float(score), x=int(box[0][0]), y=int(min(ys)), h=int(max(ys) - min(ys)))
            )
        return sorted(lines, key=lambda l: (l.y, l.x))
