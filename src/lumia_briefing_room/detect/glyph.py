from __future__ import annotations

import numpy as np

V_LO = 120
S_HI = 70


def text_score(rgb: np.ndarray, *, v_lo: int = V_LO, s_hi: int = S_HI) -> np.ndarray:
    """픽셀마다 '흰 글자일 가능성'을 0~1 로 매긴다. (plan.md §5.5)

    이진화하지 않는다 — 값이 바뀐 직후 새 숫자가 흐리게 나타났다가
    서서히 진해지는 구간(research §4.5)을 통째로 잃지 않기 위해서다.
    """
    a = rgb.astype(np.int16)
    v = a.max(axis=-1)
    s = v - a.min(axis=-1)
    bright = np.clip((v - v_lo) / (255 - v_lo), 0.0, 1.0)
    achroma = np.clip(1.0 - s / s_hi, 0.0, 1.0)
    return (bright * achroma).astype(np.float32)


def build_template(samples: np.ndarray) -> np.ndarray:
    """같은 숫자의 RGB 크롭 여러 장 (N,H,W,3) -> 숫자 본보기 (H,W) 0~1.

    글자는 흰색이 배경 위에 겹쳐진 것이라 배경이 다양할수록 하위 퍼센타일이
    실제 진하기(알파)에 가까워진다. 이상치 한 장에 흔들리지 않도록 최솟값
    대신 하위 10 퍼센타일을 쓴다.
    """
    v = samples.astype(np.int16).max(axis=-1)
    return np.clip(np.percentile(v, 10, axis=0) / 255.0, 0.0, 1.0).astype(np.float32)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """평균을 뺀 뒤 정규화한 상관계수. 둘 다 같은 shape 이어야 한다."""
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.sqrt((a * a).sum() * (b * b).sum()))
    if denom < 1e-6:
        return 0.0
    return float((a * b).sum() / denom)
