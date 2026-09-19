from lumia_briefing_room.detect.intervals import to_intervals


def s(t: float, combat: bool | None) -> tuple[float, bool | None]:
    return (t, combat)


def test_판독불가는_교전을_끊지_않는다():
    states = [s(0, True), s(3, True), s(6, None), s(9, True), s(12, True)]
    assert to_intervals(states) == [(0.0, 12.0)]


def test_짧은_교전은_버린다():
    states = [s(0, False), s(3, True), s(6, False), s(9, False)]
    assert to_intervals(states) == []


def test_짧은_off_구간은_메워서_하나로_합친다():
    states = [s(0, True), s(3, True), s(6, False), s(9, True), s(12, True)]
    assert to_intervals(states) == [(0.0, 12.0)]


def test_긴_off_구간은_메우지_않고_두_구간으로_남긴다():
    states = [
        s(0, True), s(3, True),
        s(6, False), s(9, False), s(12, False),
        s(15, True), s(18, True),
    ]
    intervals = to_intervals(states, gap_fill_samples=2)
    assert intervals == [(0.0, 3.0), (15.0, 18.0)]


def test_전부_판독불가면_교전_없음으로_본다():
    states = [s(0, None), s(3, None), s(6, None)]
    assert to_intervals(states) == []


def test_전부_교전중이면_하나의_구간():
    states = [s(0, True), s(3, True), s(6, True)]
    assert to_intervals(states) == [(0.0, 6.0)]


def test_빈_입력은_빈_리스트():
    assert to_intervals([]) == []


def test_최소_길이_미만이면_gap_fill_후에도_버려진다():
    states = [s(0, True), s(3, False), s(6, True)]
    intervals = to_intervals(states, gap_fill_samples=2, min_combat_samples=5)
    assert intervals == []


def test_시작이_off인_경우_gap_fill_대상이_아니다():
    states = [s(0, False), s(3, True), s(6, True)]
    assert to_intervals(states) == [(3.0, 6.0)]


def test_끝이_off인_경우_gap_fill_대상이_아니다():
    states = [s(0, True), s(3, True), s(6, False)]
    assert to_intervals(states) == [(0.0, 3.0)]
