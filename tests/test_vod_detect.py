from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.pipeline.vod_detect import detect_games
from lumia_briefing_room.pipeline.vod_games import split_games


def fs(t, *, ingame, k=None, a=0, combat=False, team_combat=None, day=1):
    return FrameState(
        t=t, combat=combat if ingame else None,
        face_value=111.0 if ingame else None, face_sat=26.0 if ingame else None,
        k=k if ingame else None, a=a if ingame else None,
        day_night="day" if ingame else None, spectating=False if ingame else None,
        game_day=day if ingame else None, team_combat=team_combat if ingame else None,
    )


def two_games(k_by_game, team_combat_by_game=(None, None)):
    states = []
    for g, (start, end) in enumerate([(100, 400), (700, 1000)]):
        k_events = k_by_game[g]
        for t in range(start - 20, end + 21):
            ingame = start <= t <= end
            k = sum(1 for et in k_events if et <= t) if ingame else None
            in_fight = ingame and any(et - 8 <= t <= et for et in k_events)
            states.append(fs(float(t), ingame=ingame, k=k, combat=in_fight,
                             team_combat=team_combat_by_game[g]))
    return states


def test_each_game_gets_its_own_counter_totals():
    states = two_games([[150, 200, 250], [750, 800]])
    spans = split_games(states)

    results = detect_games(states, spans)

    assert [r.detection.k_final for r in results] == [3, 2]
    assert [sum(i.k_delta for i in r.detection.intervals) for r in results] == [3, 2]


def test_intervals_never_cross_a_game_boundary():
    states = two_games([[150, 390], [710, 800]])
    spans = split_games(states)

    results = detect_games(states, spans)

    for r in results:
        for iv in r.detection.intervals:
            assert r.span.start <= iv.start and iv.end <= r.span.end


def test_team_combat_saturation_is_judged_per_game():
    states = two_games([[150, 250], [750, 850]], team_combat_by_game=(True, False))
    spans = split_games(states)

    results = detect_games(states, spans)

    game1, game2 = results
    assert sum(i.end - i.start for i in game1.detection.intervals) < 100
    assert len(game2.detection.intervals) == 2


def test_no_games_means_no_results():
    assert detect_games([], []) == []
