import numpy as np

from lumia_briefing_room.detect.glyph import build_template, similarity, text_score


def _solid(rgb: tuple[int, int, int], shape=(4, 4)) -> np.ndarray:
    frame = np.zeros((*shape, 3), dtype=np.uint8)
    frame[..., 0] = rgb[0]
    frame[..., 1] = rgb[1]
    frame[..., 2] = rgb[2]
    return frame


def test_text_score_high_for_pure_white():
    frame = _solid((255, 255, 255), shape=(1, 1))
    score = text_score(frame)
    assert score[0, 0] > 0.9


def test_text_score_zero_for_dark_background():
    frame = _solid((20, 15, 10), shape=(1, 1))
    score = text_score(frame)
    assert score[0, 0] == 0.0


def test_text_score_low_for_saturated_color():
    # 채도가 높은 색(글자가 아님)은 밝아도 점수가 낮아야 한다
    frame = _solid((255, 0, 0), shape=(1, 1))
    score = text_score(frame)
    assert score[0, 0] < 0.3


def test_text_score_moderate_for_faded_fadein_frame():
    # research §4.5: 값 전환 직후 새 숫자는 흐리게(밝기 169 근처) 나타난다
    frame = _solid((169, 169, 169), shape=(1, 1))
    score = text_score(frame)
    assert 0.3 < score[0, 0] < 0.9


def test_build_template_recovers_alpha_from_varied_backgrounds():
    alpha = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float32)
    rng = np.random.default_rng(0)
    samples = []
    for _ in range(20):
        bg = rng.integers(0, 120, size=(2, 2, 1)).astype(np.float32)
        composed = alpha[..., None] * 255.0 + (1 - alpha[..., None]) * bg
        samples.append(np.repeat(composed, 3, axis=2).astype(np.uint8))
    template = build_template(np.stack(samples))

    assert template[0, 1] > 0.8
    assert template[1, 0] > 0.8
    assert template[0, 0] < 0.5
    assert template[1, 1] < 0.5


def test_similarity_self_correlation_is_high():
    a = np.array([[0.0, 1.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
    assert similarity(a, a) > 0.99


def test_similarity_low_for_orthogonal_patterns():
    a = np.array([[1.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    b = np.array([[0.0, 1.0], [0.0, 1.0]], dtype=np.float32)
    assert similarity(a, b) < -0.99


def test_similarity_zero_for_flat_input():
    flat = np.ones((3, 3), dtype=np.float32)
    other = np.array(
        [[0.0, 1.0, 0.0], [1.0, 0.0, 1.0], [0.0, 1.0, 0.0]], dtype=np.float32
    )
    assert similarity(flat, other) == 0.0
