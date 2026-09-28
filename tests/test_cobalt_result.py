import numpy as np

from lumia_briefing_room.detect.cobalt_result import (
    CobaltResultScreen,
    CobaltTeammate,
    parse_teammate_panel,
    read_cobalt_outcome,
    read_cobalt_result_screen,
    to_result_screen,
)
from lumia_briefing_room.detect.ocr import TextLine
from lumia_briefing_room.detect.region import build_region_template, region_score
from lumia_briefing_room.profiles.models import ResolutionProfile

_OUTCOME_ROI = ResolutionProfile.for_resolution(1920, 1080).rois["cobalt_outcome"]
H, W = _OUTCOME_ROI.height, _OUTCOME_ROI.width


def line(text, y, score=1.0, x=30, h=30):
    return TextLine(text=text, score=score, x=x, y=y, h=h)


def _text(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    rgb = np.full((H, W, 3), 30, np.uint8)
    ink_h, ink_w = H - 25, W - 45
    ink = rng.random((ink_h, ink_w)) > 0.5
    rgb[10 : 10 + ink_h, 15 : 15 + ink_w][ink] = 255
    return rgb


OUTCOME_TEMPLATES = {
    "승리": build_region_template([region_score(_text(1))]),
    "패배": build_region_template([region_score(_text(2))]),
}

PANEL = [
    line("코발트", 10),
    line("패배", 50),
    line("|우쮸", 200),
    line("TK", 250, x=30),
    line("K", 250, x=140),
    line("D", 250, x=250),
    line("A", 250, x=360),
    line("17", 280, x=30),
    line("10", 280, x=140),
    line("7", 280, x=250),
    line("4", 280, x=360),
]

TEAMMATE = [
    line("kellin08", 20),
    line("TK", 100, x=10),
    line("K", 100, x=110),
    line("D", 100, x=210),
    line("A", 100, x=310),
    line("17", 130, x=10),
    line("3", 130, x=110),
    line("8", 130, x=210),
    line("9", 130, x=310),
]


def test_read_cobalt_outcome_reads_the_matching_word():
    assert read_cobalt_outcome(_text(1), OUTCOME_TEMPLATES) == "승리"
    assert read_cobalt_outcome(_text(2), OUTCOME_TEMPLATES) == "패배"


def test_read_cobalt_outcome_none_without_templates_or_for_a_blank_screen():
    assert read_cobalt_outcome(_text(1), {}) is None
    assert read_cobalt_outcome(np.full((H, W, 3), 30, np.uint8), OUTCOME_TEMPLATES) is None


def test_parse_teammate_panel_reads_nickname_and_stats():
    teammate = parse_teammate_panel(TEAMMATE)
    assert teammate == CobaltTeammate(nickname="kellin08", tk=17, kills=3, deaths=8, assists=9)


def test_parse_teammate_panel_handles_missing_stats():
    assert parse_teammate_panel([line("이름없음", 10)]) == CobaltTeammate(
        nickname="이름없음", tk=None, kills=None, deaths=None, assists=None
    )


def test_parse_teammate_panel_ignores_the_recommendation_badge_above_the_nickname():
    """실측(§10-1): `5/6` 추천 배지가 닉네임보다 먼저(위에) 나올 수 있다."""
    lines = [line("5/6", 20)] + TEAMMATE
    assert parse_teammate_panel(lines).nickname == "kellin08"


class FakeReader:
    """호출 순서: 패널(1회) -> 팀원 카드마다 1회."""

    def __init__(self, panel, teammates):
        self.panel = panel
        self.teammates = list(teammates)
        self.calls = []

    def read(self, rgb, *, lang="korean"):
        self.calls.append(lang)
        if len(self.calls) == 1:
            return self.panel
        return self.teammates.pop(0) if self.teammates else []


def outcome_frame(profile, word):
    frame = np.zeros((profile.height, profile.width, 3), dtype=np.uint8)
    roi = profile.rois["cobalt_outcome"]
    frame[roi.y0 : roi.y1, roi.x0 : roi.x1] = _text(1 if word == "승리" else 2)
    return frame


def test_read_cobalt_result_screen_end_to_end():
    profile = ResolutionProfile.for_resolution(1920, 1080)
    reader = FakeReader(PANEL, [TEAMMATE, TEAMMATE, TEAMMATE])

    result = read_cobalt_result_screen(outcome_frame(profile, "패배"), profile, reader, OUTCOME_TEMPLATES)

    assert result == CobaltResultScreen(
        outcome="패배",
        nickname="우쮸",
        stats={"tk": 17, "kills": 10, "deaths": 7, "assists": 4},
        teammates=[CobaltTeammate(nickname="kellin08", tk=17, kills=3, deaths=8, assists=9)] * 3,
    )


def test_read_cobalt_result_screen_returns_none_without_a_recognized_outcome():
    profile = ResolutionProfile.for_resolution(1920, 1080)
    reader = FakeReader(PANEL, [])
    blank = np.zeros((profile.height, profile.width, 3), dtype=np.uint8)

    assert read_cobalt_result_screen(blank, profile, reader, OUTCOME_TEMPLATES) is None


def test_read_cobalt_result_screen_none_without_templates():
    profile = ResolutionProfile.for_resolution(1920, 1080)
    reader = FakeReader(PANEL, [TEAMMATE, TEAMMATE, TEAMMATE])

    assert read_cobalt_result_screen(outcome_frame(profile, "패배"), profile, reader, None) is None


def test_read_cobalt_result_screen_is_none_for_a_profile_without_the_roi():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    reader = FakeReader(PANEL, [TEAMMATE, TEAMMATE, TEAMMATE])
    blank = np.zeros((profile.height, profile.width, 3), dtype=np.uint8)

    assert read_cobalt_result_screen(blank, profile, reader, OUTCOME_TEMPLATES) is None


def test_to_result_screen_maps_win_and_lose_to_a_ui_compatible_placement():
    win = CobaltResultScreen(outcome="승리", nickname="우쮸", stats={"tk": 29}, teammates=[])
    lose = CobaltResultScreen(outcome="패배", nickname="우쮸", stats={"tk": 17}, teammates=[])

    assert (to_result_screen(win).placement, to_result_screen(win).total) == (1, 2)
    assert (to_result_screen(lose).placement, to_result_screen(lose).total) == (2, 2)
    assert to_result_screen(win).outcome == "승리"
    assert to_result_screen(win).match_type == "unknown"


def test_to_result_screen_keeps_teammate_nicknames_and_stats_as_plain_dicts():
    teammates = [CobaltTeammate(nickname="kellin08", tk=17, kills=3, deaths=8, assists=9)]
    screen = to_result_screen(CobaltResultScreen(outcome="패배", nickname=None, stats={}, teammates=teammates))

    assert screen.teammates == [{"nickname": "kellin08", "character": None, "tk": 17, "kills": 3, "deaths": 8, "assists": 9}]
