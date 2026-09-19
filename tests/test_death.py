import numpy as np

from lumia_briefing_room.detect.death import FaceStat, detect_death, face_stat


def _solid(rgb: tuple[int, int, int], shape=(4, 4)) -> np.ndarray:
    frame = np.zeros((*shape, 3), dtype=np.uint8)
    frame[..., 0] = rgb[0]
    frame[..., 1] = rgb[1]
    frame[..., 2] = rgb[2]
    return frame


def test_face_stat_computes_value_and_saturation():
    frame = _solid((120, 100, 90))
    stat = face_stat(frame, t=5.0)
    assert stat.t == 5.0
    assert stat.value == 120.0
    assert stat.sat == 30.0


def test_detect_death_flags_relative_drop_against_baseline():
    # research §4.7 실측 근사: 정상 채도25.9/밝기111.4 -> 사망 채도13.3/밝기33.9
    normal = [FaceStat(t=float(i), value=111.0, sat=26.0) for i in range(10)]
    dead = [FaceStat(t=float(10 + i), value=34.0, sat=13.0) for i in range(3)]
    stats = normal + dead + normal
    intervals = detect_death(stats)
    assert intervals == [(10.0, 12.0)]


def test_detect_death_ignores_mild_fluctuation():
    stats = [
        FaceStat(t=float(i), value=v, sat=s)
        for i, (v, s) in enumerate(
            [(111, 26), (90, 22), (105, 25), (80, 20), (100, 24), (95, 23)]
        )
    ]
    assert detect_death(stats) == []


def test_detect_death_empty_input():
    assert detect_death([]) == []


def test_detect_death_requires_both_value_and_saturation_drop():
    # 밝기만 떨어지고 채도는 유지되는 경우(예: 그림자) - 사망이 아니다
    stats = [FaceStat(t=float(i), value=111.0, sat=26.0) for i in range(5)]
    stats += [FaceStat(t=float(5 + i), value=30.0, sat=25.0) for i in range(3)]
    stats += [FaceStat(t=float(8 + i), value=111.0, sat=26.0) for i in range(5)]
    assert detect_death(stats) == []
