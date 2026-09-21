from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.pipeline.vod_games import GameSpan, split_games, states_in


def fs(t, *, ingame=True, day=None, k=None, spectating=False):
    return FrameState(
        t=t, combat=None, face_value=None, face_sat=None,
        k=k if ingame else None, a=None,
        day_night="day" if ingame else None,
        spectating=spectating, game_day=day if ingame else None,
    )


def timeline(spans, *, step=1.0, total=None, days=None):
    """spans: [(start, end)] 구간은 인게임, 나머지는 로비."""
    total = total or max(e for _, e in spans) + 10
    out = []
    t = 0.0
    while t <= total:
        ingame = any(a <= t <= b for a, b in spans)
        out.append(fs(t, ingame=ingame, day=(days(t) if days else 1)))
        t += step
    return out


def test_no_ingame_frames_means_no_games():
    assert split_games([fs(t, ingame=False) for t in range(0, 200)]) == []


def test_two_games_separated_by_a_lobby_gap():
    states = timeline([(100, 700), (900, 1500)])

    games = split_games(states)

    assert [(g.start, g.end) for g in games] == [(100.0, 700.0), (900.0, 1500.0)]
    assert [g.index for g in games] == [1, 2]


def test_short_flicker_inside_a_game_does_not_split_it():
    states = timeline([(100, 400), (415, 900)])

    games = split_games(states, max_gap_sec=30.0)

    assert [(g.start, g.end) for g in games] == [(100.0, 900.0)]


def test_run_shorter_than_min_game_is_dropped():
    states = timeline([(100, 130), (500, 1100)])

    games = split_games(states, min_game_sec=60.0)

    assert [(g.start, g.end) for g in games] == [(500.0, 1100.0)]


def test_day_dropping_back_to_one_splits_back_to_back_games():
    states = []
    for i in range(0, 900):
        t = float(i)
        d = 5 if t < 400 else 1
        states.append(fs(t, ingame=True, day=d))

    games = split_games(states)

    assert len(games) == 2
    assert games[0].end < games[1].start or games[0].end + 1 == games[1].start
    assert 395 <= games[1].start <= 410


def test_single_misread_day_does_not_split():
    states = [fs(float(t), ingame=True, day=5) for t in range(0, 600)]
    states[300] = fs(300.0, ingame=True, day=1)

    assert len(split_games(states)) == 1


def test_frames_with_only_k_and_not_spectating_count_as_ingame():
    states = [
        FrameState(t=float(t), combat=None, face_value=None, face_sat=None,
                   k=1, a=0, day_night=None, spectating=False)
        for t in range(0, 300)
    ]

    assert len(split_games(states)) == 1


def test_confidence_is_share_of_ingame_frames():
    states = timeline([(0, 599)], total=599)
    for i in range(100, 130):
        states[i] = fs(float(i), ingame=False)

    (game,) = split_games(states, max_gap_sec=60.0)

    assert 0.9 < game.confidence < 1.0


def test_states_in_returns_frames_inside_the_span_only():
    states = timeline([(100, 700)])
    span = GameSpan(index=1, start=100.0, end=700.0, confidence=1.0)

    inside = states_in(states, span)

    assert inside[0].t == 100.0 and inside[-1].t == 700.0
