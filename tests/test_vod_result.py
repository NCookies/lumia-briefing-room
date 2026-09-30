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
        outcome="최종 생존", nickname="x", stats={"tk": 1}, image=None,
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


class DenseSource(FakeSource):
    def frames(self):
        try:
            for t in sorted(self.frames_by_t):
                if self.start <= t <= self.end:
                    self.yielded += 1
                    yield t, self.frames_by_t[t]
        finally:
            self.closed = True


def make_dense(frames_by_t):
    made = []

    def factory(start, end):
        src = DenseSource(start, end, frames_by_t)
        made.append((start, end, src))
        return src

    return factory, made


def test_dense_pass_rereads_around_the_keyframe_hit_and_uses_its_merged_result():
    sparse = {100.0 + i: frame(200 if i == 0 else 0) for i in range(0, 60)}
    sparse[108.0] = frame(100)
    dense = {t: frame(101) for t in [107.0, 108.0, 109.0]}
    factory, _ = make(sparse)
    dense_factory, dense_made = make_dense(dense)

    def read_by_value(f):
        v = int(f[0, 0, 0])
        return result(9) if v == 100 else result(3) if v == 101 else None

    found = scan_game_end(factory, SPAN, None, read=read_by_value, is_ingame=is_ingame, dense_factory=dense_factory)

    assert found.placement == 3
    assert dense_made[0][:2] == (105.0, 120.0)


def test_dense_pass_scans_the_first_seconds_after_the_game_when_keyframes_found_nothing():
    factory, _ = make({100.0 + i: frame(0) for i in range(0, 60)})
    dense_factory, dense_made = make_dense({102.0: frame(100), 102.5: frame(100)})

    found = scan_game_end(factory, SPAN, None, read=read, is_ingame=is_ingame, dense_factory=dense_factory)

    assert found is not None
    assert dense_made[0][:2] == (100.0, 130.0)


def test_dense_pass_never_looks_past_the_next_game_start():
    factory, _ = make({})
    dense_factory, dense_made = make_dense({})

    scan_game_end(factory, SPAN, 110.0, read=read, is_ingame=is_ingame, dense_factory=dense_factory)

    assert dense_made[0][:2] == (100.0, 110.0)


def test_keyframe_result_is_kept_when_the_dense_pass_reads_nothing():
    sparse = {100.0 + i: frame(0) for i in range(0, 60)}
    sparse[108.0] = frame(100)
    factory, _ = make(sparse)
    dense_factory, _ = make_dense({})

    found = scan_game_end(factory, SPAN, None, read=read, is_ingame=is_ingame, dense_factory=dense_factory)

    assert found is not None and found.placement == 1


def test_result_time_is_the_first_frame_where_the_result_screen_was_read():
    frames = {100.0 + i: frame(200 if i == 0 else 0) for i in range(0, 100)}
    frames[108.0] = frame(100)
    factory, _ = make(frames)

    found = scan_game_end(factory, SPAN, None, read=read, is_ingame=is_ingame)

    assert found.t == 108.0


def test_result_time_comes_from_the_dense_pass_when_there_is_one():
    sparse = {100.0 + i: frame(200 if i == 0 else 0) for i in range(0, 60)}
    sparse[108.0] = frame(100)
    dense = {t: frame(101) for t in [107.5, 108.0, 109.0]}
    factory, _ = make(sparse)
    dense_factory, _ = make_dense(dense)

    def read_by_value(f):
        return result(3) if int(f[0, 0, 0]) in (100, 101) else None

    found = scan_game_end(factory, SPAN, None, read=read_by_value, is_ingame=is_ingame, dense_factory=dense_factory)

    assert found.t == 107.5
