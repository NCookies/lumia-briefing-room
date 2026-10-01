from lumia_briefing_room.detect.types import FrameState
from lumia_briefing_room.pipeline.vod_games import GameSpan, is_ingame, split_games, states_in


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


def test_is_ingame_true_from_cobalt_phase_alone():
    """plan.md §10 C2: 이 스트리머의 K/spectating 판독이 못 미더워도 Phase 판독만으로 인게임이다."""
    state = FrameState(
        t=0.0, combat=None, face_value=None, face_sat=None, k=None, a=None,
        day_night=None, spectating=None, cobalt_phase=1,
    )
    assert is_ingame(state) is True


def test_split_games_uses_cobalt_phase_when_k_and_spectating_are_unreadable():
    states = [
        FrameState(
            t=float(t), combat=None, face_value=None, face_sat=None, k=None, a=None,
            day_night=None, spectating=None, cobalt_phase=1,
        )
        for t in range(0, 300)
    ]

    assert len(split_games(states)) == 1


def test_states_in_returns_frames_inside_the_span_only():
    states = timeline([(100, 700)])
    span = GameSpan(index=1, start=100.0, end=700.0, confidence=1.0)

    inside = states_in(states, span)

    assert inside[0].t == 100.0 and inside[-1].t == 700.0


def _sel(t):
    return FrameState(t=t, combat=None, face_value=None, face_sat=None, k=None, a=None, day_night=None, select_screen=True)


def _with_selection(states, select_times):
    by_t = {s.t: s for s in states}
    for t in select_times:
        by_t[t] = _sel(t)
    return [by_t[t] for t in sorted(by_t)]


def _times(a, b, step=3.0):
    return [a + i * step for i in range(int((b - a) / step) + 1)]


def _game_with_selection(select_spans, game, step=3.0):
    times = [t for a, b in select_spans for t in _times(a, b, step)]
    return _with_selection(timeline([game], step=step), times)


def test_game_start_extends_back_to_first_frame_of_selection_cluster():
    states = _game_with_selection([(500.0, 600.0)], (624.0, 1900.0), step=3.0)
    (game,) = split_games(states)
    assert game.start == 624.0
    assert game.select_start == 500.0


def test_selection_without_a_following_game_is_a_dodge_and_ignored():
    states = _game_with_selection([(100.0, 160.0), (500.0, 600.0)], (624.0, 1900.0), step=3.0)
    (game,) = split_games(states)
    assert game.select_start == 500.0


def test_selection_too_far_before_the_game_is_not_attached():
    states = _game_with_selection([(100.0, 160.0)], (624.0, 1900.0), step=3.0)
    (game,) = split_games(states)
    assert game.select_start is None


def test_selection_cluster_tolerates_a_few_missed_frames():
    states = _game_with_selection([(500.0, 530.0), (542.0, 600.0)], (624.0, 1900.0), step=3.0)
    (game,) = split_games(states)
    assert game.select_start == 500.0


def test_selection_does_not_reach_into_the_previous_game():
    states = _with_selection(timeline([(0.0, 700.0), (800.0, 1900.0)], step=3.0), _times(711.0, 768.0))
    first, second = split_games(states)
    assert first.select_start is None
    assert second.select_start == 711.0


def test_selection_cluster_marked_practice_marks_the_game_as_practice():
    states = _game_with_selection([(500.0, 600.0)], (624.0, 1900.0), step=3.0)
    states = [
        FrameState(**{**s.__dict__, "select_practice": True}) if s.select_screen else s for s in states
    ]
    (game,) = split_games(states)
    assert game.practice is True and game.select_start == 500.0


def test_normal_selection_is_not_practice():
    (game,) = split_games(_game_with_selection([(500.0, 600.0)], (624.0, 1900.0), step=3.0))
    assert game.practice is False


def test_lobby_frames_misread_as_day_icon_do_not_stretch_the_game_end_past_the_result_screen():
    """실측(2026-10-01, 치지직 1080p 게임 11): 결과 화면(15562초) 뒤 로비 그림이 낮/밤 아이콘으로 세 장 읽혀 게임 끝이 15589초로
    늘어났고, 결과 탐색이 게임 끝 뒤부터라 결과 화면을 놓쳤다."""
    game = [fs(t, day=4) for t in range(100, 558)]
    lobby = [fs(t, ingame=False) for t in range(558, 600)]
    for i, s in enumerate(lobby):
        if s.t in (580, 587, 589):
            lobby[i] = FrameState(
                t=s.t, combat=None, face_value=None, face_sat=None, k=None, a=None,
                day_night="day", spectating=True, game_day=None,
            )

    games = split_games(game + lobby)

    assert [(g.start, g.end) for g in games] == [(100.0, 557.0)]


def test_a_game_read_only_from_the_day_icon_keeps_its_end():
    states = [fs(t, day=None) for t in range(100, 300)]

    assert [(g.start, g.end) for g in split_games(states)] == [(100.0, 299.0)]
