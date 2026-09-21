from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from lumia_briefing_room.detect.glyph import similarity

MIN_SCORE = 0.5
MIN_MARGIN = 0.05
NMS_RADIUS = 8
CONFIRM_SAMPLES = 2


@dataclass(frozen=True)
class ReadResult:
    value: int | None
    confidence: float


def _slide_correlate(score_map: np.ndarray, template: np.ndarray) -> np.ndarray:
    """template 을 score_map 위에서 가로로 슬라이드하며 위치별 유사도를 낸다."""
    th, tw = template.shape
    h, w = score_map.shape
    if h != th or w < tw:
        return np.array([])
    return np.array(
        [similarity(score_map[:, x : x + tw], template) for x in range(w - tw + 1)]
    )


def read_field(
    score_map: np.ndarray,
    templates: dict[int, np.ndarray],
    *,
    max_digits: int = 2,
    nms_radius: int = NMS_RADIUS,
    min_score: float = MIN_SCORE,
    min_margin: float = MIN_MARGIN,
) -> ReadResult:
    """ROI 전체를 슬라이딩 매칭해 숫자를 읽는다. (plan.md §5.5)

    자릿수를 먼저 판정하지 않고 전체를 훑어 피크를 묶는다 — research §4.2:
    자릿수가 늘면 필드 중심 기준으로 확장되어 우측 정렬이 아니기 때문이다.
    """
    if not templates:
        return ReadResult(value=None, confidence=0.0)

    digit_ids = sorted(templates)
    curves = {d: _slide_correlate(score_map, templates[d]) for d in digit_ids}
    n_positions = min((len(c) for c in curves.values()), default=0)
    if n_positions == 0:
        return ReadResult(value=None, confidence=0.0)

    best_digit = np.full(n_positions, -1, dtype=int)
    best_score = np.full(n_positions, -1.0, dtype=float)
    margin = np.full(n_positions, -1.0, dtype=float)
    for x in range(n_positions):
        ranked = sorted(((curves[d][x], d) for d in digit_ids), reverse=True)
        best_score[x], best_digit[x] = ranked[0]
        margin[x] = ranked[0][0] - ranked[1][0] if len(ranked) > 1 else ranked[0][0]

    candidates = [
        x
        for x in range(n_positions)
        if best_score[x] >= min_score and margin[x] >= min_margin
    ]
    if not candidates:
        return ReadResult(value=None, confidence=0.0)

    peaks: list[int] = []
    for x in candidates:
        if peaks and x - peaks[-1] < nms_radius:
            if best_score[x] > best_score[peaks[-1]]:
                peaks[-1] = x
            continue
        peaks.append(x)

    if not peaks or len(peaks) > max_digits:
        return ReadResult(value=None, confidence=0.0)

    digits = "".join(str(best_digit[x]) for x in peaks)
    confidence = float(np.clip(min(best_score[x] for x in peaks), 0.0, 1.0))
    return ReadResult(value=int(digits), confidence=confidence)


def save_templates(templates: dict[int, np.ndarray], path: Path) -> None:
    np.savez(path, **{str(d): t for d, t in templates.items()})


def load_templates(path: Path) -> dict[int, np.ndarray]:
    data = np.load(path)
    return {int(k): data[k] for k in data.files}


@dataclass(frozen=True)
class CounterEvent:
    t: float
    field: str
    frm: int
    to: int
    delta: int


def _confirmed_transitions(
    readings: list[tuple[float, int | None]], confirm_samples: int
):
    """확정값이 바뀔 때마다 (시각, 이전값, 새값) 을 낸다. 이전값이 None 이면 첫 확정(기준값)이다.

    규칙:
      1) None(신뢰도 낮음/판독 실패)은 스트릭을 끊는다. 보간하지 않는다
      2) 같은 값이 confirm_samples 연속이어야 확정값이 된다
      3) 확정값은 매치 내에서 줄지 않는다(단조) — 감소는 오판으로 버린다
      4) 시각은 그 값이 처음 보인 프레임이다(확정된 프레임이 아니라)
    """
    confirmed: int | None = None
    pending_value: int | None = None
    pending_count = 0
    pending_first_t = 0.0

    for t, v in readings:
        if v is None:
            pending_value = None
            pending_count = 0
            continue

        if v == pending_value:
            pending_count += 1
        else:
            pending_value = v
            pending_count = 1
            pending_first_t = t

        if pending_count < confirm_samples:
            continue

        if confirmed is None:
            confirmed = v
            yield (pending_first_t, None, v)
            continue

        if v == confirmed or v < confirmed:
            continue

        yield (pending_first_t, confirmed, v)
        confirmed = v


def to_events(
    readings: list[tuple[float, int | None]],
    field: str,
    *,
    confirm_samples: int = CONFIRM_SAMPLES,
) -> list[CounterEvent]:
    """확정된 값이 바뀔 때만 이벤트를 만든다. (plan.md §5.5)

    첫 확정값은 매치 시작 시점의 기존 상태로 보고 이벤트를 만들지 않는다.
    """
    return [
        CounterEvent(t=t, field=field, frm=frm, to=to, delta=to - frm)
        for t, frm, to in _confirmed_transitions(readings, confirm_samples)
        if frm is not None
    ]


def final_confirmed_value(
    readings: list[tuple[float, int | None]],
    *,
    confirm_samples: int = CONFIRM_SAMPLES,
) -> int | None:
    """스트림 전체에서 마지막으로 확정된 값. 변화가 없어도(예: 킬 0회) 값을 낸다."""
    result: int | None = None
    for _, _frm, to in _confirmed_transitions(readings, confirm_samples):
        result = to
    return result
