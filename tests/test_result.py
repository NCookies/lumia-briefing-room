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


def test_read_result_screen_resolves_clipped_character_name_from_table():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    calls = {"n": 0}

    class Reader(FakeReader):
        def read(self, rgb, *, lang="korean"):
            calls["n"] += 1
            if calls["n"] > 3:
                return [line("MARKU", 0, 0.97)]
            return super().read(rgb, lang=lang)

    result = read_result_screen(
        blank_frame(profile), profile, Reader(PANEL, [line("랭크", 5)]), {"MARKUS": "마커스"}
    )

    assert result.character == "마커스"
    assert result.character_raw == "MARKU"


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

    result = read_result_screen(frame, profile, FakeReader(PANEL, [line("랭크", 5)]), {})

    assert result.image is frame
    assert result == read_result_screen(blank_frame(profile), profile, FakeReader(PANEL, [line("랭크", 5)]), {})
