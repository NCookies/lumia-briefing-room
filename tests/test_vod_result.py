import numpy as np

from lumia_briefing_room.detect.result import ResultScreen
from lumia_briefing_room.pipeline.vod_games import GameSpan
from lumia_briefing_room.pipeline.vod_result import scan_game_end


class FakeSource:
    def __init__(self, start, end, frames_by_t):
        self.width, self.height = 8, 8
        self.start, self.end = start, end
        self.frames_by_t = frames_by_t
        self.yielded = 0
        self.closed = False

    def gaps(self):
        return []

    def frames(self):
        try:
            t = self.start
            while t <= self.end and t in self.frames_by_t:
                self.yielded += 1
                yield t, self.frames_by_t[t]
                t += 1.0
        finally:
            self.closed = True


def frame(value):
    return np.full((8, 8, 3), value, dtype=np.uint8)


def result(placement=1):
    return ResultScreen(
        placement=placement, total=7, match_type="rank", match_label="랭크",
        outcome="최종 생존", nickname="x", character="마티나", character_raw="MARTIN",
        stats={"tk": 1}, image=None,
    )


def make(frames_by_t):
    made = []

    def factory(start, end):
        src = FakeSource(start, end, frames_by_t)
        made.append((start, end, src))
        return src

    return factory, made


def is_ingame(f):
    return int(f[0, 0, 0]) == 200


def read(f):
    return result() if int(f[0, 0, 0]) == 100 else None


SPAN = GameSpan(index=1, start=10.0, end=100.0, confidence=1.0)


def test_finds_the_result_screen_after_the_game_and_stops_reading_early():
    frames = {100.0 + i: frame(200 if i == 0 else 0) for i in range(0, 100)}
    frames[108.0] = frame(100)
    factory, made = make(frames)

    found = scan_game_end(factory, SPAN, None, read=read, is_ingame=is_ingame)

    assert found is not None and found.placement == 1
    assert made[0][2].closed is True
    assert made[0][2].yielded < 100


def test_window_is_capped_by_next_game_start_and_window_length():
    factory, made = make({})
    scan_game_end(factory, SPAN, 130.0, read=read, is_ingame=is_ingame, window_sec=300.0)
    scan_game_end(factory, SPAN, None, read=read, is_ingame=is_ingame, window_sec=60.0)
    scan_game_end(factory, SPAN, 900.0, read=read, is_ingame=is_ingame, window_sec=60.0)

    assert [(s, e) for s, e, _ in made] == [(100.0, 130.0), (100.0, 160.0), (100.0, 160.0)]


def test_returns_none_when_no_result_screen_appears():
    frames = {100.0 + i: frame(0) for i in range(0, 50)}
    factory, _ = make(frames)

    assert scan_game_end(factory, SPAN, None, read=read, is_ingame=is_ingame) is None


def test_ingame_frames_are_not_read():
    calls = []

    def counting_read(f):
        calls.append(int(f[0, 0, 0]))
        return None

    frames = {100.0 + i: frame(200) for i in range(0, 30)}
    factory, _ = make(frames)

    scan_game_end(factory, SPAN, None, read=counting_read, is_ingame=is_ingame)

    assert calls == []
