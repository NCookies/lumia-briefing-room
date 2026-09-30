from pathlib import Path

from lumia_briefing_room.config import ClipConfig, Config, PathsConfig
from lumia_briefing_room.detect.types import CombatInterval
from lumia_briefing_room.pipeline.clip import ClipRange
from lumia_briefing_room.pipeline.orchestrator import (
    _aggregate_interval,
    _plan_clips,
    _resolve_clip_paths,
    default_title,
    next_phase_clip_index,
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


def test_default_title_uses_cobalt_phase_instead_of_unknown():
    """코발트 프로토콜은 낮/밤·일차가 없어 day_night=None 이 되고, 예전엔 "알 수 없음
    교전"이 됐다(실사용 보고, 2026-09-28) - 이미 읽고 있는 Phase 번호를 대신 쓴다."""
    assert default_title(None, cobalt_phase=2) == "Phase 2 교전"
    assert default_title(None, "경찰서", cobalt_phase=2) == "Phase 2 경찰서 교전"
    assert default_title(None, cobalt_phase=2, characters=["우쮸"]) == "Phase 2 교전 · 우쮸"


def test_default_title_game_day_wins_over_cobalt_phase_if_both_given():
    assert default_title("day", game_day=3, cobalt_phase=2) == "3일차 낮 교전"


def test_default_title_never_shows_day_night_for_cobalt_even_if_it_was_read():
    """실사용 보고(2026-09-28): "Phase 3 낮 교전"처럼 코발트인데 낮/밤이 붙어 나왔다.
    day_night 는 모드와 무관하게 매 프레임 읽으므로(§2.7) 코발트 화면에서 우연히 뭔가
    읽힐 수 있다 - cobalt_phase 가 있으면 day_night 값과 무관하게 절대 안 보여준다."""
    assert default_title("day", cobalt_phase=3) == "Phase 3 교전"
    assert default_title("night", cobalt_phase=3) == "Phase 3 교전"


def test_default_title_appends_a_clip_index_for_cobalt_only():
    """§10-13 이후 코발트 한 게임에 목숨마다 클립이 생겨 같은 Phase 에서 여러 번 죽으면
    제목이 겹친다 - clip_index 로 뒤에 번호를 붙여 구분한다(사용자 요청, 2026-09-28)."""
    assert default_title(None, cobalt_phase=1, clip_index=1) == "Phase 1 교전 - 1"
    assert default_title(None, cobalt_phase=1, clip_index=2) == "Phase 1 교전 - 2"
    assert default_title(None, cobalt_phase=1, characters=["우쮸"], clip_index=1) == "Phase 1 교전 · 우쮸 - 1"
    # 배틀로얄은 번호를 안 붙인다 - 배지·킬 이벤트로 이미 짧게 나뉘어 겹칠 일이 없다.
    assert default_title("day", game_day=3, clip_index=1) == "3일차 낮 교전"


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


def test_aggregate_interval_keeps_the_known_cobalt_phase():
    a = ci(0, 10, {"kill"})
    b = ci(15, 25, {"assist"})
    b = CombatInterval(**{**b.__dict__, "cobalt_phase": 2})
    assert _aggregate_interval([a, b]).cobalt_phase == 2
    assert _aggregate_interval([b, a]).cobalt_phase == 2


def test_next_phase_clip_index_resets_when_the_phase_changes():
    """실사용 보고(2026-09-28, 스크린샷): "Phase 2 교전 - 3"처럼 게임 전체 순번이 붙어
    있었다 - Phase 가 바뀌면 그 Phase 안에서 다시 1부터 세야 한다."""
    counts: dict[int | None, int] = {}
    assert next_phase_clip_index(counts, 1) == 1
    assert next_phase_clip_index(counts, 1) == 2
    assert next_phase_clip_index(counts, 2) == 1
    assert next_phase_clip_index(counts, 3) == 1
    assert next_phase_clip_index(counts, 3) == 2
    assert next_phase_clip_index(counts, 3) == 3
    # 같은 Phase 로 돌아오면(코발트에선 안 일어나지만) 이어서 센다 - 새로 만나는
    # 값마다 독립적인 카운터이지, "가장 최근 Phase"만 특별 취급하지 않는다.
    assert next_phase_clip_index(counts, 1) == 3


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


def test_plan_clips_cobalt_mode_skips_preroll_postroll_so_short_death_gaps_stay_separate():
    """실사용 사고(2026-09-28): 코발트 구간(§10-13, 부활~사망)은 죽어있는 시간만큼만
    떨어져 있는데(실측 15~21초), preroll+postroll(기본 5+8=13초)을 더하면 남는 간격이
    mergeGapSec(기본 10초) 밑으로 내려가 옆 구간과 다시 합쳐져 게임 전체가 클립 하나로
    뭉쳐버렸다. 코발트는 preroll/postroll 을 아예 안 더해야 이 간격이 안 줄어든다."""
    cfg = ClipConfig(preroll_sec=5, postroll_sec=8, merge_gap_sec=10)
    intervals = [ci(183, 282, {"kill", "death"}), ci(297, 414, {"assist", "death"})]

    battle_royale_plans = _plan_clips(intervals, cfg, game_mode="battle_royale")
    assert len(battle_royale_plans) == 1  # 옛 동작: preroll/postroll 로 간격이 줄어 합쳐진다

    cobalt_plans = _plan_clips(intervals, cfg, game_mode="cobalt")
    assert len(cobalt_plans) == 2
    assert (cobalt_plans[0].range.start, cobalt_plans[0].range.end) == (183, 282)
    assert (cobalt_plans[1].range.start, cobalt_plans[1].range.end) == (297, 414)


def test_resolve_clip_range_cobalt_mode_uses_the_interval_bounds_exactly():
    cfg = ClipConfig(preroll_sec=5, postroll_sec=8)
    from lumia_briefing_room.pipeline.clip import resolve_clip_range

    iv = ci(100, 200, {"death"})
    assert resolve_clip_range(iv, cfg, game_mode="cobalt") == ClipRange(start=100, end=200, preroll_source="combat")


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


def test_read_result_scans_the_tail_of_the_range_when_the_end_is_the_lobby_return(monkeypatch):
    """로그 기반 경기는 끝이 로비 복귀라 구간 끝에서 거슬러 오른다(기존 동작)."""
    from lumia_briefing_room.pipeline import orchestrator as orch
    from lumia_briefing_room.video.segments import SegmentRange

    calls = []
    monkeypatch.setattr(orch, "find_result_screen", lambda session, seg_range, **kw: calls.append(("tail", seg_range)) or "R")
    monkeypatch.setattr(orch, "find_result_after", lambda *a, **kw: calls.append(("after", a, kw)) or "X")

    assert orch._read_result("session", SegmentRange(10, 50), Path("ffmpeg"), None) == "R"
    assert [c[0] for c in calls] == ["tail"]


def test_read_result_scans_forward_from_the_game_end_for_screen_based_windows(monkeypatch):
    """화면으로 찾은 경기는 끝이 '마지막 인게임 프레임'이라 그 뒤에서 앞으로 훑어야 결과 화면이 잡힌다(실측: 순위가 비었다)."""
    from datetime import datetime, timedelta, timezone

    from lumia_briefing_room.pipeline import orchestrator as orch
    from lumia_briefing_room.video.segments import SegmentRange

    class Session:
        start_utc = datetime(2026, 9, 24, 6, 0, 0, tzinfo=timezone.utc)
        segment_duration_sec = 3.0

    calls = []
    monkeypatch.setattr(orch, "find_result_screen", lambda *a, **kw: calls.append("tail") or "R")

    def fake_after(session, after_segment, **kw):
        calls.append(("after", after_segment, kw["before_segment"]))
        return "X"

    monkeypatch.setattr(orch, "find_result_after", fake_after)
    game_end = Session.start_utc + timedelta(seconds=300)

    got = orch._read_result(Session(), SegmentRange(10, 130), Path("ffmpeg"), None, search_from=game_end)

    assert got == "X"
    assert calls == [("after", 101, 131)]


def test_read_result_reads_the_full_video_tail_first_and_skips_the_keyframe_scan(monkeypatch):
    from lumia_briefing_room.pipeline import orchestrator as orch
    from lumia_briefing_room.video.segments import SegmentRange

    calls = []
    monkeypatch.setattr(orch, "find_result_in_video", lambda path, **kw: calls.append(("video", path)) or "T")
    monkeypatch.setattr(orch, "find_result_screen", lambda *a, **kw: calls.append("keyframes") or "R")

    got = orch._read_result("session", SegmentRange(10, 50), Path("ffmpeg"), None, full_video=Path("full.mp4"))

    assert got == "T"
    assert calls == [("video", Path("full.mp4"))]


def test_read_result_falls_back_to_keyframes_when_the_tail_finds_nothing_or_fails(monkeypatch):
    from lumia_briefing_room.pipeline import orchestrator as orch
    from lumia_briefing_room.video.segments import SegmentRange

    monkeypatch.setattr(orch, "find_result_screen", lambda *a, **kw: "R")
    monkeypatch.setattr(orch, "find_result_in_video", lambda *a, **kw: None)
    assert orch._read_result("s", SegmentRange(10, 50), Path("ffmpeg"), None, full_video=Path("f.mp4")) == "R"

    def boom(*a, **kw):
        raise RuntimeError("ffmpeg 실패")

    monkeypatch.setattr(orch, "find_result_in_video", boom)
    assert orch._read_result("s", SegmentRange(10, 50), Path("ffmpeg"), None, full_video=Path("f.mp4")) == "R"


def test_read_result_without_full_video_reads_the_last_segments_past_the_logged_end(monkeypatch):
    from lumia_briefing_room.pipeline import orchestrator as orch
    from lumia_briefing_room.pipeline.result_scan import RESULT_TAIL_SEGMENTS
    from lumia_briefing_room.video.segments import SegmentRange

    calls = []
    monkeypatch.setattr(
        orch, "find_result_in_segments", lambda session, last, **kw: calls.append(last) or "T"
    )

    got = orch._read_result("s", SegmentRange(10, 50), Path("ffmpeg"), None, tmp_dir=Path("tmp"))

    assert got == "T"
    assert calls == [50 + RESULT_TAIL_SEGMENTS]


def test_read_result_failure_is_swallowed_in_both_modes(monkeypatch):
    from datetime import datetime, timezone

    from lumia_briefing_room.pipeline import orchestrator as orch
    from lumia_briefing_room.video.segments import SegmentRange

    class Session:
        start_utc = datetime(2026, 9, 24, 6, 0, 0, tzinfo=timezone.utc)
        segment_duration_sec = 3.0

    def boom(*a, **kw):
        raise RuntimeError("OCR 실패")

    monkeypatch.setattr(orch, "find_result_screen", boom)
    monkeypatch.setattr(orch, "find_result_after", boom)

    assert orch._read_result(Session(), SegmentRange(1, 9), Path("ffmpeg"), None) is None


def test_process_match_reports_progress_through_detection_result_scan_and_cutting(tmp_path, monkeypatch):
    """B8 (3): process_match 가 검출 프레임 진행률 → 결과 화면 판독 → 클립 컷을 순서대로,
    뒤로 가지 않게 보고하는지 (실측 비중은 orchestrator.DETECTION_PROGRESS_FRACTION 등 참고)."""
    from datetime import datetime, timezone

    from lumia_briefing_room.pipeline import orchestrator as orch
    from lumia_briefing_room.pipeline.clip import CutResult

    class Session:
        start_utc = datetime(2026, 9, 24, 6, 0, 0, tzinfo=timezone.utc)
        segment_duration_sec = 3.0
        width = 2560
        height = 1440
        directory = Path("bg_1049590_20260924_060000")

    interval = ci(0.0, 10.0, {"kill"})

    def fake_detect_match(session, seg_range, *, on_progress=None, **kwargs):
        if on_progress is not None:
            for i in (1, 2, 4):
                on_progress(i, 4)
        return orch.MatchDetection(
            intervals=[interval], k_final=1, a_final=0, gaps=[],
            source_incomplete=False, spectator_ranges=[], teammate_deaths=0,
        )

    monkeypatch.setattr(orch, "detect_match", fake_detect_match)
    monkeypatch.setattr(orch, "_read_result", lambda *a, **kw: None)
    monkeypatch.setattr(
        orch, "cut_clip",
        lambda *a, **kw: CutResult(segment_start=1, segment_end=4, duration_sec=10.0, source_incomplete=False),
    )
    monkeypatch.setattr(orch, "make_thumbnail", lambda *a, **kw: None)
    monkeypatch.setattr(orch, "write_metadata", lambda meta, path: None)

    seen: list[float] = []
    written = orch.process_match(
        Session(), Session.start_utc, Session.start_utc, Config(paths=PathsConfig(clips=tmp_path)),
        ffmpeg_path=Path("ffmpeg"), clips_dir=tmp_path, on_progress=seen.append,
    )

    assert len(written) == 1
    assert seen == sorted(seen)
    assert seen[-1] == 1.0
    assert any(0 < v < orch.DETECTION_PROGRESS_FRACTION for v in seen), seen
    assert orch.DETECTION_PROGRESS_FRACTION in seen
    assert orch.RESULT_SCAN_PROGRESS_FRACTION in seen


class _FakeSession:
    from datetime import datetime as _dt, timezone as _tz

    start_utc = _dt(2026, 9, 24, 6, 0, 0, tzinfo=_tz.utc)
    segment_duration_sec = 3.0
    width = 2560
    height = 1440
    directory = Path("bg_1049590_20260924_060000")


def _patch_pipeline(monkeypatch, orch, *, intervals, full_ok=True, markers=()):
    from lumia_briefing_room.pipeline.clip import CutResult
    from lumia_briefing_room.pipeline.full_video import FullVideo, FullVideoOutcome

    cuts: list[str] = []

    def fake_detect_match(session, seg_range, *, on_progress=None, **kwargs):
        return orch.MatchDetection(
            intervals=list(intervals), k_final=1, a_final=0, gaps=[],
            source_incomplete=False, spectator_ranges=[], teammate_deaths=[], markers=list(markers),
        )

    def fake_full(session, seg_range, start, end, folder, **kw):
        cuts.append("full")
        if not full_ok:
            return FullVideoOutcome(None, "저장 공간이 부족해 풀영상을 만들지 못했습니다")
        cut = CutResult(segment_start=2, segment_end=5, duration_sec=12.0, source_incomplete=False)
        return FullVideoOutcome(FullVideo(path=folder / "full.mp4", cut=cut, size_bytes=5, offset_sec=3.0))

    def fake_cut(session, rng, out, **kw):
        cuts.append(out.stem)
        return CutResult(segment_start=1, segment_end=4, duration_sec=10.0, source_incomplete=False)

    monkeypatch.setattr(orch, "detect_match", fake_detect_match)
    monkeypatch.setattr(orch, "cut_full_video", fake_full)
    monkeypatch.setattr(orch, "cut_clip", fake_cut)
    monkeypatch.setattr(orch, "_read_result", lambda *a, **kw: None)
    monkeypatch.setattr(orch, "_find_portraits", lambda *a, **kw: None)
    monkeypatch.setattr(orch, "make_thumbnail", lambda *a, **kw: None)
    return cuts


def _run_process(orch, tmp_path, *, save_mode="auto", **kw):
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp"), clip=ClipConfig(save_mode=save_mode))
    start = _FakeSession.start_utc
    written = orch.process_match(
        _FakeSession(), start, start, cfg, ffmpeg_path=Path("ffmpeg"), clips_dir=tmp_path / "clips",
        games_dir=tmp_path / "games", **kw,
    )
    import json
    game = json.loads((tmp_path / "games" / "20260924_060000" / "game.json").read_text(encoding="utf-8"))
    return written, game


def test_process_match_records_the_game_even_when_nothing_passes_the_filter(tmp_path, monkeypatch):
    from lumia_briefing_room.pipeline import orchestrator as orch

    _patch_pipeline(monkeypatch, orch, intervals=[])
    seen: list[float] = []
    written, game = _run_process(orch, tmp_path, on_progress=seen.append)

    assert written == []
    assert game["candidates"] == []
    assert game["fullVideo"]["path"] == "full.mp4"
    assert seen[-1] == 1.0


def test_full_video_is_cut_before_any_clip_and_candidates_are_relative_to_it(tmp_path, monkeypatch):
    from lumia_briefing_room.pipeline import orchestrator as orch

    cuts = _patch_pipeline(monkeypatch, orch, intervals=[ci(10.0, 20.0, {"kill"})], markers=[(12.0, "kill")])
    written, game = _run_process(orch, tmp_path)

    assert cuts[0] == "full" and len(written) == 1
    (cand,) = game["candidates"]
    assert (cand["start"], cand["end"]) == (2.0, 25.0)
    assert cand["user"] == {"savedClipId": "20260924_060000_01"}
    assert game["markers"] == [{"t": 9.0, "kind": "kill"}]
    assert game["saveMode"] == "auto"


def test_manual_save_mode_records_candidates_but_cuts_no_clips(tmp_path, monkeypatch):
    from lumia_briefing_room.pipeline import orchestrator as orch

    cuts = _patch_pipeline(monkeypatch, orch, intervals=[ci(10.0, 20.0, {"kill"})])
    written, game = _run_process(orch, tmp_path, save_mode="manual")

    assert written == [] and cuts == ["full"]
    assert game["candidates"][0]["user"] == {}


def test_when_the_full_video_fails_only_certain_candidates_become_clips_and_the_error_is_recorded(tmp_path, monkeypatch):
    from lumia_briefing_room.pipeline import orchestrator as orch

    intervals = [ci(10.0, 20.0, {"kill"}), ci(200.0, 210.0, {"no_result"})]
    cuts = _patch_pipeline(monkeypatch, orch, intervals=intervals, full_ok=False)
    errors: list[str] = []
    written, game = _run_process(orch, tmp_path, save_mode="manual", on_full_video_error=errors.append)

    assert len(written) == 1
    assert errors and "저장 공간이 부족" in errors[0]
    assert game["fullVideo"] is None and "저장 공간이 부족" in game["fullVideoError"]
    assert len(game["candidates"]) == 2
    assert game["candidates"][0]["user"] and not game["candidates"][1]["user"]
