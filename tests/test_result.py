import numpy as np

from lumia_briefing_room.detect.ocr import TextLine
from lumia_briefing_room.detect.result import (
    ResultScreen,
    clean_nickname,
    parse_panel,
    read_result_screen,
)
from lumia_briefing_room.profiles.models import ResolutionProfile


def line(text, y, score=1.0, x=30, h=30):
    return TextLine(text=text, score=score, x=x, y=y, h=h)


PANEL = [
    line("4/7", 40),
    line("실험 종료", 220),
    line("|내테스트닉", 370),
    line("TK", 420),
    line("13", 450),
    line("흥미로운 결과라고 해두자.", 600),
]


def test_parse_panel_reads_placement_total_outcome_and_nickname_line():
    parsed = parse_panel(PANEL)

    assert parsed.placement == 4
    assert parsed.total == 7
    assert parsed.outcome == "실험 종료"
    assert parsed.nickname_line.text == "|내테스트닉"


def test_parse_panel_tolerates_spaces_around_slash_and_stray_lines_before_placement():
    parsed = parse_panel([line("+1", 5), line("1 / 8", 40), line("최종 생존", 220)])

    assert (parsed.placement, parsed.total, parsed.outcome) == (1, 8, "최종 생존")


def test_parse_panel_skips_low_confidence_noise_between_placement_and_outcome():
    parsed = parse_panel([line("4/7", 40), line("이", 150, 0.51), line("실험 종료", 220)])

    assert parsed.outcome == "실험 종료"


def test_parse_panel_prefers_line_right_above_nickname_over_chip_text():
    parsed = parse_panel(
        [line("7/7", 40), line("랭크 대전", 182), line("실험 종료", 225), line("|내테스트닉", 372)]
    )

    assert parsed.outcome == "실험 종료"


def test_parse_panel_returns_none_without_placement():
    assert parse_panel([line("TK", 10), line("13", 40)]) is None


def test_parse_panel_rejects_placement_larger_than_total():
    assert parse_panel([line("9/7", 40), line("실험 종료", 220)]) is None


def test_clean_nickname_strips_bar_prefix_but_keeps_cjk_and_latin():
    assert clean_nickname("|내테스트닉") == "내테스트닉"
    assert clean_nickname("{ TeamMateB ") == "TeamMateB"
    assert clean_nickname("| 東京タワー") == "東京タワー"


class FakeReader:
    def __init__(self, panel, chip, nickname=None):
        self.panel, self.chip, self.nickname = panel, chip, nickname
        self.calls = []

    def read(self, rgb, *, lang="korean"):
        self.calls.append(lang)
        n = len(self.calls)
        if n == 1:
            return self.panel
        if n == 2:
            return self.chip
        if self.nickname is None:
            return []
        return [self.nickname.get(lang, line("", 0, 0.0))]


def blank_frame(profile):
    return np.zeros((profile.height, profile.width, 3), dtype=np.uint8)


def test_read_result_screen_marks_rank_game_from_chip_text():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    reader = FakeReader(PANEL, [line("랭크", 5)])

    result = read_result_screen(blank_frame(profile), profile, reader)

    assert result == ResultScreen(
        placement=4, total=7, match_type="rank", match_label="랭크",
        outcome="실험 종료", nickname="내테스트닉",
        stats={"tk": None, "kills": None, "deaths": None, "assists": None},
    )


def test_read_result_screen_treats_other_chip_as_normal_game():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    reader = FakeReader(PANEL, [line("일반", 5)])

    result = read_result_screen(blank_frame(profile), profile, reader)

    assert result.match_type == "normal"
    assert result.match_label == "일반"


def test_read_result_screen_marks_type_unknown_when_chip_is_unreadable():
    profile = ResolutionProfile.for_resolution(2560, 1440)

    result = read_result_screen(blank_frame(profile), profile, FakeReader(PANEL, []))

    assert result.match_type == "unknown"
    assert result.placement == 4


def test_read_result_screen_returns_none_when_not_a_result_screen():
    profile = ResolutionProfile.for_resolution(2560, 1440)

    assert read_result_screen(blank_frame(profile), profile, FakeReader([line("나가기", 5)], [])) is None


def test_read_result_screen_prefers_higher_scoring_language_for_nickname():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    reader = FakeReader(
        PANEL,
        [line("랭크", 5)],
        nickname={"korean": line("東京タリー", 0, 0.55), "ch": line("東京タワー", 0, 0.98)},
    )

    result = read_result_screen(blank_frame(profile), profile, reader)

    assert result.nickname == "東京タワー"


def test_read_result_screen_keeps_the_frame_without_affecting_equality():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = blank_frame(profile)

    result = read_result_screen(frame, profile, FakeReader(PANEL, [line("랭크", 5)]))

    assert result.image is frame
    assert result == read_result_screen(blank_frame(profile), profile, FakeReader(PANEL, [line("랭크", 5)]))


class ChipSequenceReader:
    """패널 → (칩 읽기 시도들) → 닉네임 순으로 답하고, 칩 시도 횟수를 센다."""

    def __init__(self, chip_attempts):
        self.chip_attempts = list(chip_attempts)
        self.calls = 0

    def read(self, rgb, *, lang="korean"):
        self.calls += 1
        if self.calls == 1:
            return PANEL
        if self.calls - 2 < len(self.chip_attempts):
            return self.chip_attempts[self.calls - 2]
        return []


def test_chip_is_read_from_plain_upscale_first_without_trying_binarized():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    reader = ChipSequenceReader([[line("일반", 5)], [line("랭크", 5)]])

    result = read_result_screen(blank_frame(profile), profile, reader)

    assert (result.match_type, result.match_label) == ("normal", "일반")


def test_chip_falls_back_to_binarized_when_plain_upscale_reads_nothing():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    reader = ChipSequenceReader([[], [line("랭크 대전", 5)]])

    result = read_result_screen(blank_frame(profile), profile, reader)

    assert (result.match_type, result.match_label) == ("rank", "랭크 대전")


UNREADABLE_RANK_PANEL = [
    line("L/E", 41, 0.81),
    line("실험 종료", 225, 0.99),
    line("|내테스트닉", 372),
    line("TK", 426, x=84),
    line("K", 427, x=207),
    line("D", 430, x=323),
    line("A", 426, x=438),
    line("13", 456, x=86),
    line("4", 457, x=208),
    line("2", 458, x=322),
    line("5", 457, x=437),
]


def test_parse_panel_keeps_rest_when_placement_is_unreadable():
    parsed = parse_panel(UNREADABLE_RANK_PANEL)

    assert (parsed.placement, parsed.total) == (None, None)
    assert parsed.outcome == "실험 종료"
    assert parsed.nickname_line.text == "|내테스트닉"
    assert parsed.stats == {"tk": 13, "kills": 4, "deaths": 2, "assists": 5}


def test_parse_panel_without_placement_needs_nickname_and_stats():
    assert parse_panel([line("실험 종료", 225), line("|내테스트닉", 372)]) is None
    assert parse_panel([line("실험 종료", 225), line("TK", 426), line("13", 456)]) is None


def test_read_result_screen_saves_result_without_placement():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    reader = FakeReader(UNREADABLE_RANK_PANEL, [line("일반", 5)])

    result = read_result_screen(blank_frame(profile), profile, reader)

    assert result.placement is None and result.total is None
    assert (result.match_type, result.outcome, result.nickname) == ("normal", "실험 종료", "내테스트닉")
    assert result.stats["tk"] == 13


def test_parse_panel_without_outcome_line_does_not_crash():
    parsed = parse_panel([line("4/7", 40), line("|내테스트닉", 372)])
    assert parsed.outcome is None and parsed.nickname_line.text == "|내테스트닉"
    assert parse_panel([line("TK", 10), line("|닉", 20)]) is None


def screen(**kw):
    base = dict(
        placement=3, total=7, match_type="normal", match_label="일반", outcome="실험 종료", nickname="나",
        stats={"tk": 13, "kills": 4, "deaths": 2, "assists": 5}, image=None,
    )
    base.update(kw)
    return ResultScreen(**base)


def test_merge_takes_the_majority_of_each_field_separately():
    from lumia_briefing_room.detect.result import merge_results

    merged = merge_results([
        screen(placement=8, nickname="나X"),
        screen(placement=3, match_type="unknown", match_label="", nickname="나"),
        screen(placement=3, nickname="나"),
        screen(placement=3, outcome=None, stats={"tk": 13, "kills": 4, "deaths": 9, "assists": 5}),
    ])

    assert (merged.placement, merged.total) == (3, 7)
    assert (merged.match_type, merged.match_label) == ("normal", "일반")
    assert merged.outcome == "실험 종료"
    assert merged.nickname == "나"
    assert merged.stats == {"tk": 13, "kills": 4, "deaths": 2, "assists": 5}


def test_merge_ignores_unreadable_values_when_any_frame_read_them():
    from lumia_briefing_room.detect.result import merge_results

    merged = merge_results([
        screen(placement=None, total=None, stats={"tk": None, "kills": 4, "deaths": None, "assists": None}),
        screen(placement=1, total=7),
    ])

    assert merged.placement == 1
    assert merged.stats["kills"] == 4 and merged.stats["tk"] == 13


def test_merge_keeps_placement_empty_when_no_frame_read_it():
    from lumia_briefing_room.detect.result import merge_results

    merged = merge_results([screen(placement=None, total=None), screen(placement=None, total=None)])

    assert merged.placement is None and merged.total is None


def test_merge_uses_the_image_of_the_frame_with_most_fields_read():
    from lumia_briefing_room.detect.result import merge_results

    poor, rich = np.zeros((1, 1, 3), np.uint8), np.ones((1, 1, 3), np.uint8)

    merged = merge_results([
        screen(placement=None, match_type="unknown", match_label="", image=poor),
        screen(image=rich),
    ])

    assert merged.image is rich


def test_merge_of_one_screen_and_of_nothing():
    from lumia_briefing_room.detect.result import merge_results

    one = screen()
    assert merge_results([one]) == one
    assert merge_results([]) is None
