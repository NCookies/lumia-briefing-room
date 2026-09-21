import numpy as np
import pytest

from lumia_briefing_room.detect.counter import (
    CounterEvent,
    ReadResult,
    final_confirmed_value,
    read_field,
    to_events,
)
from lumia_briefing_room.detect.glyph import build_template, text_score


def _build_digit_templates(render_digit, compose, *, count=30, seed=0):
    rng = np.random.default_rng(seed)
    templates = {}
    for digit in range(10):
        alpha = render_digit(digit)
        samples = []
        for _ in range(count):
            bg = tuple(int(x) for x in rng.integers(0, 180, size=3))
            samples.append(compose(alpha, bg))
        templates[digit] = build_template(np.stack(samples))
    return templates


def _roi_with_digits(compose, digits_alpha: list[np.ndarray], *, gap: int, pad: int,
                      background: tuple[int, int, int]) -> np.ndarray:
    height = digits_alpha[0].shape[0]
    total_width = pad + sum(a.shape[1] for a in digits_alpha) + gap * (len(digits_alpha) - 1) + pad
    alpha = np.zeros((height, total_width), dtype=np.float32)
    x = pad
    for a in digits_alpha:
        w = a.shape[1]
        alpha[:, x : x + w] = a
        x += w + gap
    return compose(alpha, background)


def test_read_field_reads_single_digit_with_padding(render_digit, compose):
    templates = _build_digit_templates(render_digit, compose)
    roi = _roi_with_digits(compose, [render_digit(1)], gap=0, pad=6, background=(60, 40, 90))
    score = text_score(roi)

    result = read_field(score, templates, max_digits=2)

    assert isinstance(result, ReadResult)
    assert result.value == 1
    assert result.confidence > 0


def test_read_field_reads_two_digits(render_digit, compose):
    templates = _build_digit_templates(render_digit, compose)
    roi = _roi_with_digits(
        compose, [render_digit(1), render_digit(0)], gap=1, pad=4, background=(30, 70, 50)
    )
    score = text_score(roi)

    result = read_field(score, templates, max_digits=2)

    assert result.value == 10


def test_read_field_returns_none_for_blank_roi(render_digit, compose):
    templates = _build_digit_templates(render_digit, compose)
    blank = np.full((17, 30, 3), 80, dtype=np.uint8)
    score = text_score(blank)

    result = read_field(score, templates, max_digits=2)

    assert result.value is None


def test_read_field_returns_none_without_templates():
    score = np.zeros((17, 30), dtype=np.float32)
    result = read_field(score, {}, max_digits=2)
    assert result.value is None
    assert result.confidence == 0.0


def r(t: float, v: int | None) -> tuple[float, int | None]:
    return (t, v)


def test_단일_프레임_오판은_이벤트를_만들지_않는다():
    readings = [r(0.0, 2), r(0.5, 2), r(1.0, 9), r(1.5, 2), r(2.0, 2)]
    assert to_events(readings, "K") == []


def test_이벤트_시각은_처음_보인_프레임():
    readings = [r(0.0, 2), r(0.5, 2), r(1.0, 3), r(1.5, 3)]
    (ev,) = to_events(readings, "K")
    assert ev.t == 1.0
    assert ev.frm == 2
    assert ev.to == 3
    assert ev.delta == 1


def test_감소는_버린다():
    readings = [r(0.0, 5), r(0.5, 5), r(1.0, 2), r(1.5, 2), r(2.0, 5), r(2.5, 5)]
    assert to_events(readings, "K") == []


def test_none은_스트릭을_끊는다():
    readings = [
        r(0.0, 0), r(0.5, 0),          # 기준값 0 확정 (조용히, 이벤트 없음)
        r(1.0, 2), r(1.5, None),        # 2 가 한 번 보였다가 None 에 끊긴다
        r(2.0, 2), r(2.5, 2),           # 여기서 다시 2 스트릭이 시작돼 확정된다
    ]
    (ev,) = to_events(readings, "K")
    # 1.0 의 단발성 2 는 무효화됐으므로 이벤트 시각은 2.0 이어야 한다
    assert ev.t == 2.0
    assert ev.frm == 0
    assert ev.to == 2


def test_field_이름이_이벤트에_기록된다():
    readings = [r(0.0, 0), r(0.5, 0), r(1.0, 1), r(1.5, 1)]
    (ev,) = to_events(readings, "A")
    assert ev.field == "A"


def test_빈_readings는_빈_이벤트_목록():
    assert to_events([], "K") == []


def test_final_confirmed_value_without_any_change():
    readings = [r(0.0, 0), r(0.5, 0), r(1.0, 0)]
    assert final_confirmed_value(readings) == 0


def test_final_confirmed_value_reflects_last_confirmed():
    readings = [r(0.0, 0), r(0.5, 0), r(1.0, 3), r(1.5, 3), r(2.0, 9), r(2.5, 9)]
    assert final_confirmed_value(readings) == 9


def test_final_confirmed_value_ignores_unconfirmed_trailing_noise():
    readings = [r(0.0, 0), r(0.5, 0), r(1.0, 3), r(1.5, 3), r(2.0, 99)]
    assert final_confirmed_value(readings) == 3


def test_final_confirmed_value_none_when_never_confirmed():
    assert final_confirmed_value([r(0.0, 1)]) is None


def test_counter_event_is_frozen():
    ev = CounterEvent(t=0.0, field="K", frm=0, to=1, delta=1)
    with pytest.raises(Exception):
        ev.t = 1.0  # type: ignore[misc]


def test_two_digit_templates_add_10_to_99_and_keep_single_digits():
    from lumia_briefing_room.detect.counter import with_two_digit_templates

    single = {d: np.full((4, 12), d / 10, dtype=np.float32) for d in range(10)}

    expanded = with_two_digit_templates(single, shift=2)

    assert set(expanded) == set(range(100))
    for d in range(10):
        assert np.array_equal(expanded[d], single[d])
    assert expanded[12].shape == single[1].shape


def test_two_digit_template_places_tens_left_and_ones_right():
    from lumia_briefing_room.detect.counter import with_two_digit_templates

    tens = np.zeros((2, 8), dtype=np.float32)
    tens[:, 3:5] = 1.0
    ones = np.zeros((2, 8), dtype=np.float32)
    ones[:, 3:5] = 0.5
    single = {d: tens if d == 1 else ones for d in range(10)}

    expanded = with_two_digit_templates(single, shift=2)

    row = expanded[12][0]
    assert row[1] == 1.0 and row[2] == 1.0
    assert row[5] == 0.5 and row[6] == 0.5
    assert row[3] == 0.0 and row[4] == 0.0


def test_read_field_reads_a_two_digit_value_from_composite_templates(render_digit, compose):
    from lumia_briefing_room.detect.counter import with_two_digit_templates

    templates = _build_digit_templates(render_digit, compose)
    expanded = with_two_digit_templates(templates, shift=6)
    score = expanded[12]

    result = read_field(score, expanded, max_digits=2)

    assert result.value == 12


def test_single_digit_field_is_still_read_as_a_single_digit_with_expanded_templates(render_digit, compose):
    from lumia_briefing_room.detect.counter import with_two_digit_templates

    templates = _build_digit_templates(render_digit, compose)
    expanded = with_two_digit_templates(templates, shift=6)

    for digit in range(10):
        assert read_field(templates[digit], expanded, max_digits=2).value == digit
