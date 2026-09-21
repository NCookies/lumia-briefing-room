from lumia_briefing_room.detect.ocr import TextLine
from lumia_briefing_room.detect.result import parse_panel


def line(text, x, y, score=1.0):
    return TextLine(text=text, score=score, x=x, y=y, h=30)


BASE = [line("4/7", 30, 40), line("실험 종료", 30, 220), line("|내테스트닉", 30, 372)]
LABELS = [line("TK", 84, 426), line("K", 205, 427), line("D", 323, 428), line("A", 435, 428)]


def stats_of(values):
    return parse_panel(BASE + LABELS + values).stats


def test_parse_panel_reads_tk_k_d_a_by_column_under_each_label():
    values = [line("13", 84, 457), line("3", 208, 457), line("1", 323, 457), line("6", 438, 457)]

    assert stats_of(values) == {"tk": 13, "kills": 3, "deaths": 1, "assists": 6}


def test_parse_panel_keeps_zero_values_and_ignores_noise_below_min_score():
    values = [line("2", 84, 457), line("0", 208, 457, 0.68), line("4", 323, 457), line("0", 438, 457, 0.3)]

    assert stats_of(values) == {"tk": 2, "kills": 0, "deaths": 4, "assists": None}


def test_parse_panel_stats_are_empty_without_labels():
    assert stats_of([]) == {"tk": None, "kills": None, "deaths": None, "assists": None}


def test_parse_panel_ignores_numbers_far_below_the_stat_row():
    values = [line("13", 84, 900), line("3", 208, 457), line("1", 323, 457), line("6", 438, 457)]

    assert stats_of(values)["tk"] is None
