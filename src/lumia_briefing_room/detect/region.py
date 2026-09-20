from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

V_LO = 170
INK_MIN = 0.15
MIN_SCORE = 0.6
MIN_MARGIN = 0.1


@dataclass(frozen=True)
class RegionRead:
    name: str | None
    confidence: float


def region_score(rgb: np.ndarray, *, v_lo: int = V_LO) -> np.ndarray:
    """SPEC §2.10: 헤더 글자의 진하기를 0~1 로. 색은 보지 않는다.

    금지구역 예정이면 글자가 흰색에서 주황으로 바뀌므로 K/A 판독의 무채도 항을 쓰지 않는다.
    """
    v = rgb.astype(np.int16).max(axis=-1)
    return np.clip((v - v_lo) / (255 - v_lo), 0.0, 1.0).astype(np.float32)


def build_region_template(samples: list[np.ndarray]) -> np.ndarray:
    mean = np.mean(np.stack(samples), axis=0)
    cols = np.where(mean.max(axis=0) > INK_MIN)[0]
    if len(cols) == 0:
        return mean
    return mean[:, cols[0] : cols[-1] + 1].astype(np.float32)


def _correlations(score: np.ndarray, template: np.ndarray) -> np.ndarray:
    """템플릿을 0 으로 채워 ROI 폭에 맞춘 뒤 x 위치마다 잰 정규화 상관계수.

    ROI 전체를 비교하므로 템플릿 밖의 글자(접두어만 같은 다른 이름)가 점수를 깎는다.
    영패딩 템플릿의 통계는 x 와 무관해서 matchTemplate 한 번으로 닫힌 형태로 풀린다.
    """
    n = score.size
    ccorr = cv2.matchTemplate(score, template, cv2.TM_CCORR)[0]
    mean_s = float(score.mean())
    mean_p = float(template.sum() / n)
    cov = ccorr - n * mean_s * mean_p
    var_s = float((score * score).sum() - n * mean_s * mean_s)
    var_p = float((template * template).sum() - n * mean_p * mean_p)
    denom = np.sqrt(max(var_s, 0.0) * max(var_p, 0.0))
    if denom < 1e-6:
        return np.zeros_like(cov)
    return cov / denom


def read_region(
    score: np.ndarray,
    templates: dict[str, np.ndarray],
    *,
    min_score: float = MIN_SCORE,
    min_margin: float = MIN_MARGIN,
) -> RegionRead:
    """헤더 점수맵을 지역명 템플릿과 대조한다. 글자 폭 전체를 비교해 접두어 오인을 막는다."""
    if not templates:
        return RegionRead(name=None, confidence=0.0)

    score = np.ascontiguousarray(score, dtype=np.float32)
    h, w = score.shape
    best: dict[str, float] = {}
    for name, template in templates.items():
        th, tw = template.shape
        if th != h or tw > w:
            continue
        best[name] = float(_correlations(score, np.ascontiguousarray(template, dtype=np.float32)).max())

    if not best:
        return RegionRead(name=None, confidence=0.0)
    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    top_name, top_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    if top_score < min_score or top_score - runner_up < min_margin:
        return RegionRead(name=None, confidence=0.0)
    return RegionRead(name=top_name, confidence=float(np.clip(top_score, 0.0, 1.0)))


def save_region_templates(templates: dict[str, np.ndarray], path: Path) -> None:
    np.savez(path, **templates)


def load_region_templates(path: Path) -> dict[str, np.ndarray]:
    data = np.load(path)
    return {name: data[name] for name in data.files}
