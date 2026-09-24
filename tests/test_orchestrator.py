from pathlib import Path

from lumia_briefing_room.config import ClipConfig, Config, PathsConfig
from lumia_briefing_room.detect.types import CombatInterval
from lumia_briefing_room.pipeline.clip import ClipRange
from lumia_briefing_room.pipeline.orchestrator import (
    _aggregate_interval,
    _plan_clips,
    _resolve_clip_paths,
    default_title,
)


def ci(start, end, tags, day_night="day", died=False, confidence=1.0):
    return CombatInterval(
        start=start, end=end, tags=frozenset(tags),
        k_delta=1 if "kill" in tags else 0,
        a_delta=1 if "assist" in tags else 0,
        died=died, day_night=day_night, confidence=confidence,
    )


def test_default_title_day():
    assert default_title("day") == "낮 교전"


def test_default_title_night():
    assert default_title("night") == "밤 교전"


def test_default_title_unknown():
    assert default_title(None) == "알 수 없음 교전"


def test_aggregate_interval_unions_tags():
    a = ci(0, 10, {"kill"})
    b = ci(15, 25, {"assist"})
    agg = _aggregate_interval([a, b])
    assert agg.tags == frozenset({"kill", "assist"})
    assert agg.start == 0
    assert agg.end == 25
    assert agg.k_delta == 1
    assert agg.a_delta == 1


def test_aggregate_interval_died_if_any():
    a = ci(0, 10, {"kill"}, died=False)
    b = ci(15, 25, {"death"}, died=True)
    agg = _aggregate_interval([a, b])
    assert agg.died is True


def test_aggregate_interval_confidence_is_minimum():
    a = ci(0, 10, {"kill"}, confidence=0.9)
    b = ci(15, 25, {"assist"}, confidence=0.5)
    agg = _aggregate_interval([a, b])
    assert agg.confidence == 0.5


def test_aggregate_single_interval_passthrough():
    a = ci(0, 10, {"kill"})
    agg = _aggregate_interval([a])
    assert agg == a


def test_plan_clips_keeps_separate_when_far_apart():
    cfg = ClipConfig(preroll_sec=5, postroll_sec=8, merge_gap_sec=10)
    intervals = [ci(0, 10, {"kill"}), ci(200, 210, {"assist"})]
    plans = _plan_clips(intervals, cfg)
    assert len(plans) == 2
    assert [len(p.intervals) for p in plans] == [1, 1]


def test_plan_clips_merges_close_intervals_into_one():
    cfg = ClipConfig(preroll_sec=5, postroll_sec=8, merge_gap_sec=15)
    # 첫 클립 범위: [0-5, 10+8] = [-5, 18] -> clamp [0, 18]
    # 둘째 교전 시작 25 는 18+15=33 이내라 병합된다
    intervals = [ci(0, 10, {"kill"}), ci(25, 35, {"assist"})]
    plans = _plan_clips(intervals, cfg)
    assert len(plans) == 1
    assert len(plans[0].intervals) == 2
    assert plans[0].range.end == 43  # 35 + postroll 8


def test_plan_clips_empty_input():
    cfg = ClipConfig()
    assert _plan_clips([], cfg) == []


def test_resolve_clip_paths_thumbnails_follow_explicit_clips_dir_override():
    # 회귀 테스트: clips_dir 를 오버라이드했는데 썸네일이 cfg.paths.clips
    # (설정 파일 기본 경로)를 따라가던 버그. 실제 녹화본으로 처음 돌려봤을 때
    # 지정한 clips_dir 가 아니라 %USERPROFILE%\Videos\... 에 썸네일이 생겨 발견했다.
    cfg = Config()
    clips_root, thumbnails_root = _resolve_clip_paths(cfg, Path("D:/my_clips"))
    assert clips_root == Path("D:/my_clips")
    assert thumbnails_root == Path("D:/my_clips/.thumbs")


def test_resolve_clip_paths_uses_default_when_no_override():
    cfg = Config()
    clips_root, thumbnails_root = _resolve_clip_paths(cfg, None)
    assert thumbnails_root == clips_root / ".thumbs"


def test_resolve_clip_paths_respects_explicit_thumbnails_config():
    cfg = Config(paths=PathsConfig(thumbnails=Path("E:/custom_thumbs")))
    clips_root, thumbnails_root = _resolve_clip_paths(cfg, Path("D:/my_clips"))
    assert thumbnails_root == Path("E:/custom_thumbs")


def test_plan_clips_sorts_out_of_order_input():
    cfg = ClipConfig(preroll_sec=5, postroll_sec=8, merge_gap_sec=10)
    intervals = [ci(200, 210, {"assist"}), ci(0, 10, {"kill"})]
    plans = _plan_clips(intervals, cfg)
    assert len(plans) == 2
    assert plans[0].range.start < plans[1].range.start


def test_aggregate_interval_sums_teammate_deaths():
    from lumia_briefing_room.detect.types import CombatInterval
    from lumia_briefing_room.pipeline.orchestrator import _aggregate_interval

    def iv(start, end, deaths):
        return CombatInterval(
            start=start, end=end, tags=frozenset({"teammate_death"}), k_delta=0, a_delta=0,
            died=False, day_night="day", confidence=1.0, teammate_deaths=deaths,
        )

    merged = _aggregate_interval([iv(0, 5, 1), iv(8, 12, 2)])

    assert merged.teammate_deaths == 3


def test_aggregate_interval_averages_enemy_ring_means_and_keeps_first_region():
    from lumia_briefing_room.detect.types import CombatInterval
    from lumia_briefing_room.pipeline.orchestrator import _aggregate_interval

    def iv(start, end, rings, region):
        return CombatInterval(
            start=start, end=end, tags=frozenset({"no_result"}), k_delta=0, a_delta=0,
            died=False, day_night="day", confidence=1.0, enemy_ring_mean=rings, region=region,
        )

    merged = _aggregate_interval([iv(0, 5, 1.0, None), iv(8, 12, None, "묘지"), iv(14, 20, 2.0, "성당")])

    assert merged.enemy_ring_mean == 1.5
    assert merged.region == "묘지"


def test_aggregate_interval_takes_the_strongest_ultimate_delta():
    from lumia_briefing_room.detect.types import CombatInterval
    from lumia_briefing_room.pipeline.orchestrator import _aggregate_interval

    def iv(start, end, ultimate):
        return CombatInterval(
            start=start, end=end, tags=frozenset({"no_result"}), k_delta=0, a_delta=0,
            died=False, day_night="day", confidence=1.0, ultimate_delta=ultimate,
        )

    merged = _aggregate_interval([iv(0, 5, 0.1), iv(8, 12, None), iv(14, 20, 0.5)])

    assert merged.ultimate_delta == 0.5


def test_aggregate_interval_ultimate_delta_is_none_when_never_read():
    from lumia_briefing_room.detect.types import CombatInterval
    from lumia_briefing_room.pipeline.orchestrator import _aggregate_interval

    def iv(start, end):
        return CombatInterval(
            start=start, end=end, tags=frozenset({"no_result"}), k_delta=0, a_delta=0,
            died=False, day_night="day", confidence=1.0,
        )

    assert _aggregate_interval([iv(0, 5), iv(8, 12)]).ultimate_delta is None


def test_aggregate_interval_team_combat_unreliable_if_any_sub_interval_is():
    from lumia_briefing_room.detect.types import CombatInterval
    from lumia_briefing_room.pipeline.orchestrator import _aggregate_interval

    def iv(start, end, unreliable):
        return CombatInterval(
            start=start, end=end, tags=frozenset({"no_result"}), k_delta=0, a_delta=0,
            died=False, day_night="day", confidence=1.0, team_combat_unreliable=unreliable,
        )

    assert _aggregate_interval([iv(0, 5, False), iv(8, 12, True)]).team_combat_unreliable is True
    assert _aggregate_interval([iv(0, 5, False), iv(8, 12, False)]).team_combat_unreliable is False


def test_default_title_includes_region_when_known():
    from lumia_briefing_room.pipeline.orchestrator import default_title

    assert default_title("day", "묘지") == "낮 묘지 교전"
    assert default_title("night") == "밤 교전"


def test_aggregate_interval_drops_no_result_when_another_tag_exists():
    from lumia_briefing_room.detect.types import CombatInterval
    from lumia_briefing_room.pipeline.orchestrator import _aggregate_interval

    def iv(tags):
        return CombatInterval(
            start=0, end=5, tags=frozenset(tags), k_delta=0, a_delta=0,
            died=False, day_night="day", confidence=1.0,
        )

    assert _aggregate_interval([iv({"no_result"}), iv({"assist"})]).tags == frozenset({"assist"})
    assert _aggregate_interval([iv({"no_result"}), iv({"no_result"})]).tags == frozenset({"no_result"})


def test_default_title_puts_the_day_before_day_night():
    from lumia_briefing_room.pipeline.orchestrator import default_title

    assert default_title("day", "묘지", 4) == "4일차 낮 묘지 교전"
    assert default_title("night", None, 6) == "6일차 밤 교전"
    assert default_title("night", "성당") == "밤 성당 교전"


def test_aggregate_interval_keeps_the_first_known_game_day():
    from lumia_briefing_room.detect.types import CombatInterval
    from lumia_briefing_room.pipeline.orchestrator import _aggregate_interval

    def iv(day):
        return CombatInterval(
            start=0, end=5, tags=frozenset({"no_result"}), k_delta=0, a_delta=0,
            died=False, day_night="day", confidence=1.0, game_day=day,
        )

    assert _aggregate_interval([iv(None), iv(4), iv(5)]).game_day == 4
