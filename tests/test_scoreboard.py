import numpy as np

from lumia_briefing_room.detect.ocr import TextLine
from lumia_briefing_room.detect.scoreboard import (
    BoardRow,
    find_team,
    group_rows,
    merge_passes,
    read_scoreboard,
    recover_character,
    snap_character,
)
from lumia_briefing_room.profiles.models import ResolutionProfile

ROSTER = {"루치아": "루치아", "엘레나": "엘레나", "마르티나": "마르티나", "레녹스": "레녹스", "르노어": "르노어"}
ROSTER_NAMES = list(ROSTER)


def line(text, y, score=1.0, x=22, h=30):
    return TextLine(text=text, score=score, x=x, y=y, h=h)


def test_snap_character_accepts_exact_and_slightly_misread_names():
    assert snap_character("루치아", ROSTER_NAMES) == "루치아"
    assert snap_character("마르티아", ROSTER_NAMES) == "마르티나"
    assert snap_character(" 레녹스 ", ROSTER_NAMES) == "레녹스"


def test_snap_character_rejects_garbage_and_non_names():
    assert snap_character("TeamMateB", ROSTER_NAMES) is None
    assert snap_character("은위리", ROSTER_NAMES) is None
    assert snap_character("", ROSTER_NAMES) is None
    assert snap_character("9", ROSTER_NAMES) is None


def test_group_rows_pairs_each_nickname_with_the_subtitle_just_below_it():
    lines = [
        line("팀원가", 245), line("루치아", 278),
        line("TeamMateB", 347),
        line("내테스트닉", 442), line("마르티나", 474),
        line("TeamMateC", 540), line("레녹스", 571),
    ]

    rows = group_rows(lines, ROSTER_NAMES)

    assert [(r.nickname, r.character) for r in rows] == [
        ("팀원가", "루치아"), ("TeamMateB", None), ("내테스트닉", "마르티나"), ("TeamMateC", "레녹스"),
    ]


def test_group_rows_does_not_treat_a_garbled_subtitle_as_a_character():
    rows = group_rows([line("NKNK", 735), line("은위리", 765)], ROSTER_NAMES)

    assert [(r.nickname, r.character) for r in rows] == [("NKNK", None)]


def test_merge_passes_prefers_the_reading_that_is_a_known_character():
    good = [line("마르티나", 474, 0.9)]
    bad = [line("여채위위류", 475, 0.99)]

    merged = merge_passes([bad, good], ROSTER_NAMES)

    assert [m.text for m in merged] == ["마르티나"]


def test_merge_passes_keeps_separate_lines_that_are_far_apart_and_takes_best_score():
    a = [line("팀원가", 245, 0.7), line("TeamMateB", 347, 1.0)]
    b = [line("팀원가", 246, 0.99)]

    merged = merge_passes([a, b], ROSTER_NAMES)

    assert [(m.text, round(m.score, 2)) for m in merged] == [("팀원가", 0.99), ("TeamMateB", 1.0)]


def rows(*specs):
    return [BoardRow(rank=r, nickname=n, character=c) for r, n, c in specs]


def test_find_team_returns_teammates_with_the_same_rank_excluding_me():
    board = rows(
        (1, "팀원가", "루치아"), (1, "TeamMateB", "엘레나"), (1, "내테스트닉", "마르티나"),
        (2, "TeamMateC", "레녹스"),
    )

    me, mates = find_team(board, "내테스트닉")

    assert me.character == "마르티나"
    assert [(m.nickname, m.character) for m in mates] == [("팀원가", "루치아"), ("TeamMateB", "엘레나")]


def test_find_team_tolerates_a_slightly_different_nickname_reading():
    board = rows((4, "모리쿠보노노", "테오도르"), (4, "내테스트닉", None))

    me, mates = find_team(board, "내테스트닉")

    assert me.nickname == "내테스트닉"
    assert [m.nickname for m in mates] == ["모리쿠보노노"]


def test_find_team_gives_up_when_my_row_or_rank_is_unknown():
    assert find_team(rows((1, "a", None)), "zzzz") is None
    assert find_team(rows((None, "내테스트닉", None), (None, "b", None)), "내테스트닉") is None


class FakeReader:
    """프레임 좌표의 줄을 주면, 호출된 이미지 배율에 맞춰 크롭 좌표로 바꿔 돌려준다."""

    def __init__(self, panel, names, ranks):
        self.panel, self.names, self.ranks = panel, names, ranks
        self.calls = 0

    def read(self, rgb, *, lang="korean"):
        self.calls += 1
        if self.calls == 1:
            return self.panel
        if rgb.shape[1] in (178 * 4, 240 * 4):
            return []
        is_rank = rgb.shape[1] < 400
        scale = rgb.shape[1] / (160 if is_rank else 500)
        source = self.ranks if is_rank else self.names
        return [
            TextLine(text=l.text, score=l.score, x=l.x, y=int((l.y - 200) * scale), h=l.h)
            for l in source
        ]


def test_read_scoreboard_returns_none_when_the_left_panel_has_no_placement():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = np.zeros((1440, 2560, 3), dtype=np.uint8)

    assert read_scoreboard(frame, profile, FakeReader([line("나가기", 10)], [], []), ROSTER_NAMES) is None


def test_read_scoreboard_builds_rows_with_ranks_from_the_rank_column():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
    names = [line("팀원가", 245), line("루치아", 278), line("니키", 347)]
    ranks = [line("1", 250, x=40), line("2", 352, x=40)]
    reader = FakeReader([line("1위", 40), line("스쿼드", 100)], names, ranks)

    board = read_scoreboard(frame, profile, reader, ROSTER_NAMES)

    assert [(r.rank, r.nickname, r.character) for r in board] == [(1, "팀원가", "루치아"), (2, "니키", None)]


def test_group_rows_skips_level_numbers_between_the_nickname_and_the_subtitle():
    lines = [line("팀원가", 246), line("6", 266), line("루치아", 279), line("0", 463), line("TeamMateB", 347)]

    rows = group_rows(lines, ROSTER_NAMES)

    assert [(r.nickname, r.character) for r in rows] == [("팀원가", "루치아"), ("TeamMateB", None)]


class RetryReader:
    """처음 `succeed_after` 번은 아무것도 못 읽다가 그다음부터 부제를 읽어 주는 리더."""

    def __init__(self, succeed_after, text="엘레나"):
        self.succeed_after, self.text, self.calls = succeed_after, text, 0

    def read(self, rgb, *, lang="korean"):
        self.calls += 1
        return [line(self.text, 0)] if self.calls > self.succeed_after else []


def test_recover_character_retries_shifted_crops_until_a_known_name_is_read():
    frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
    reader = RetryReader(succeed_after=7)

    assert recover_character(frame, 347, ROSTER_NAMES, reader) == "엘레나"
    assert reader.calls > 7


def test_recover_character_gives_up_when_nothing_matches():
    frame = np.zeros((1440, 2560, 3), dtype=np.uint8)

    assert recover_character(frame, 347, ROSTER_NAMES, RetryReader(succeed_after=10**6)) is None
    assert recover_character(frame, 347, ROSTER_NAMES, RetryReader(succeed_after=0, text="은위리")) is None


def test_read_scoreboard_retries_only_rows_without_a_character():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
    names = [line("팀원가", 245), line("루치아", 278), line("TeamMateB", 347)]
    ranks = [line("1", 250, x=40), line("1", 352, x=40)]

    class Reader(FakeReader):
        def read(self, rgb, *, lang="korean"):
            if rgb.shape[1] in (178 * 4, 240 * 4):
                return [line("엘레나", 0)]
            return super().read(rgb, lang=lang)

    board = read_scoreboard(frame, profile, Reader([line("1위", 40)], names, ranks), ROSTER_NAMES)

    assert [(r.nickname, r.character) for r in board] == [("팀원가", "루치아"), ("TeamMateB", "엘레나")]


def test_read_scoreboard_can_skip_the_expensive_character_retries():
    profile = ResolutionProfile.for_resolution(2560, 1440)
    frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
    names = [line("팀원가", 245), line("루치아", 278), line("TeamMateB", 347)]
    ranks = [line("1", 250, x=40), line("1", 352, x=40)]

    class Reader(FakeReader):
        def read(self, rgb, *, lang="korean"):
            if rgb.shape[1] in (178 * 4, 240 * 4):
                raise AssertionError("재시도가 돌면 안 된다")
            return super().read(rgb, lang=lang)

    board = read_scoreboard(frame, profile, Reader([line("1위", 40)], names, ranks), ROSTER_NAMES, recover=False)

    assert [(r.nickname, r.character) for r in board] == [("팀원가", "루치아"), ("TeamMateB", None)]
