import json
from datetime import datetime, timezone
from pathlib import Path

from lumia_briefing_room.detect.types import CombatInterval
from lumia_briefing_room.pipeline.clip import ClipRange, CutResult
from lumia_briefing_room.pipeline.metadata import build_metadata, phase_index, revive_cost, write_metadata


class _FakeSession:
    directory = Path("/fake/bg_1049590_20260919_130747")
    start_utc = datetime(2026, 9, 19, 13, 7, 47, tzinfo=timezone.utc)
    width = 2560
    height = 1440


def test_phase_index_formula():
    assert phase_index(1, "day") == 0
    assert phase_index(1, "night") == 1
    assert phase_index(2, "day") == 2
    assert phase_index(2, "night") == 3
    assert phase_index(3, "day") == 4


def test_revive_cost_free_up_to_phase_3():
    assert revive_cost(0) == "free"
    assert revive_cost(3) == "free"
    assert revive_cost(4) == "credit"
    assert revive_cost(10) == "credit"


def _interval():
    return CombatInterval(
        start=8351.0, end=8378.5, tags=frozenset({"kill", "assist"}),
        k_delta=1, a_delta=1, died=False, day_night="day", confidence=0.94,
    )


def test_build_metadata_assembles_spec_schema():
    meta = build_metadata(
        title="3일차 낮 아르다, 얀, 히스이",
        session=_FakeSession(),
        match_start_utc=datetime(2026, 9, 19, 15, 22, 20, tzinfo=timezone.utc),
        game_mode="battle_royale",
        interval=_interval(),
        clip_range=ClipRange(start=8343.0, end=8386.5, preroll_source="combat"),
        cut_result=CutResult(segment_start=2782, segment_end=2795, duration_sec=39.0, source_incomplete=False),
        thumbnail_path="thumbs/0001.jpg",
        game_day=3,
    )

    assert meta.title == "3일차 낮 아르다, 얀, 히스이"
    assert meta.session_dir == "bg_1049590_20260919_130747"
    assert meta.segment_start == 2782
    assert meta.segment_end == 2795
    assert meta.duration_sec == 39.0
    assert sorted(meta.tags) == ["assist", "kill"]
    assert meta.phase_index == 4
    assert meta.revive_cost == "credit"
    assert meta.pinned is False
    assert meta.deleted_at is None


def test_build_metadata_without_game_day_leaves_phase_none():
    meta = build_metadata(
        title="3일차 낮",
        session=_FakeSession(),
        match_start_utc=datetime(2026, 9, 19, 15, 22, 20, tzinfo=timezone.utc),
        game_mode="battle_royale",
        interval=_interval(),
        clip_range=ClipRange(start=8343.0, end=8386.5, preroll_source="combat"),
        cut_result=CutResult(segment_start=2782, segment_end=2795, duration_sec=39.0, source_incomplete=False),
        thumbnail_path=None,
    )
    assert meta.game_day is None
    assert meta.phase_index is None
    assert meta.revive_cost is None


def test_write_metadata_produces_spec_camelcase_keys(tmp_path):
    meta = build_metadata(
        title="테스트",
        session=_FakeSession(),
        match_start_utc=datetime(2026, 9, 19, 15, 22, 20, tzinfo=timezone.utc),
        game_mode="battle_royale",
        interval=_interval(),
        clip_range=ClipRange(start=8343.0, end=8386.5, preroll_source="combat"),
        cut_result=CutResult(segment_start=2782, segment_end=2795, duration_sec=39.0, source_incomplete=False),
        thumbnail_path="thumbs/0001.jpg",
        game_day=3,
        match_kills=4,
        match_assists=9,
    )
    path = tmp_path / "meta.json"

    write_metadata(meta, path)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["sessionDir"] == "bg_1049590_20260919_130747"
    assert data["segmentStart"] == 2782
    assert data["videoOffsetSec"] == 8343.0
    assert data["killDelta"] == 1
    assert data["phaseIndex"] == 4
    assert data["reviveCost"] == "credit"
    assert data["matchKills"] == 4
    assert data["matchAssists"] == 9
    assert data["teamCharacters"] == []


def _build(**overrides):
    from lumia_briefing_room.detect.pvp import PvpScore

    kwargs = dict(
        title="낮 묘지 교전",
        session=_FakeSession(),
        match_start_utc=datetime(2026, 9, 19, 15, 22, 20, tzinfo=timezone.utc),
        game_mode="battle_royale",
        interval=CombatInterval(
            start=8351.0, end=8378.5, tags=frozenset({"no_result"}), k_delta=0, a_delta=0,
            died=False, day_night="day", confidence=0.9, region="묘지", enemy_ring_mean=0.8,
        ),
        clip_range=ClipRange(start=8343.0, end=8386.5, preroll_source="combat"),
        cut_result=CutResult(segment_start=2782, segment_end=2795, duration_sec=39.0, source_incomplete=False),
        thumbnail_path=None,
        pvp=PvpScore(score=0.4, signals=["enemy_rings"]),
    )
    kwargs.update(overrides)
    return build_metadata(**kwargs)


def test_metadata_carries_pvp_region_and_label_fields(tmp_path):
    meta = _build()
    path = tmp_path / "m.json"

    write_metadata(meta, path)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["pvpScore"] == 0.4
    assert data["pvpSignals"] == ["enemy_rings"]
    assert data["region"] == "묘지"
    assert data["enemyRingMean"] == 0.8
    assert data["teamWipe"] is None
    assert data["userLabel"] is None


def test_metadata_pvp_defaults_to_zero_when_not_scored():
    from lumia_briefing_room.detect.pvp import PvpScore

    meta = _build(pvp=PvpScore(score=0.0))

    assert meta.pvp_score == 0.0
    assert meta.pvp_signals == []


def test_metadata_records_audio_status_from_the_cut():
    meta = _build(cut_result=CutResult(
        segment_start=2782, segment_end=2795, duration_sec=39.0,
        source_incomplete=False, audio_status="partial",
    ))

    assert meta.audio_status == "partial"


def test_metadata_audio_status_defaults_to_full():
    assert _build().audio_status == "full"


def test_metadata_starts_without_a_label_source():
    meta = _build()

    assert meta.label_source is None
    assert meta.label_conflict is False


def test_build_metadata_uses_result_character_as_my_character():
    from lumia_briefing_room.detect.result import ResultScreen

    result = ResultScreen(
        placement=1, total=8, match_type="rank", match_label="랭크", outcome="최종 생존",
        nickname="나", character="마커스", character_raw="MARKU",
    )
    meta = build_metadata(
        title="t", session=_FakeSession(),
        match_start_utc=datetime(2026, 9, 19, 15, 22, 20, tzinfo=timezone.utc),
        game_mode="battle_royale", interval=_interval(),
        clip_range=ClipRange(start=0.0, end=10.0, preroll_source="combat"),
        cut_result=CutResult(segment_start=1, segment_end=2, duration_sec=9.0, source_incomplete=False),
        thumbnail_path=None, match_result=result,
    )

    assert meta.my_character == "마커스"
    assert meta.match_result["characterRaw"] == "MARKU"


def test_build_metadata_stores_match_result_as_camel_dict_and_defaults_to_none():
    from lumia_briefing_room.detect.result import ResultScreen

    kwargs = dict(
        title="t", session=_FakeSession(),
        match_start_utc=datetime(2026, 9, 19, 15, 22, 20, tzinfo=timezone.utc),
        game_mode="battle_royale", interval=_interval(),
        clip_range=ClipRange(start=0.0, end=10.0, preroll_source="combat"),
        cut_result=CutResult(segment_start=1, segment_end=2, duration_sec=9.0, source_incomplete=False),
        thumbnail_path=None,
    )
    result = ResultScreen(
        placement=4, total=7, match_type="rank", match_label="랭크", outcome="실험 종료", nickname="나"
    )

    assert build_metadata(**kwargs).match_result is None
    assert build_metadata(**kwargs, match_result=result).match_result == {
        "matchType": "rank", "matchLabel": "랭크", "placement": 4, "total": 7,
        "outcome": "실험 종료", "nickname": "나", "character": None, "characterRaw": None,
    }


def test_match_result_dict_includes_image_path_only_when_given():
    from lumia_briefing_room.detect.result import ResultScreen
    from lumia_briefing_room.pipeline.metadata import match_result_dict

    result = ResultScreen(
        placement=4, total=7, match_type="rank", match_label="랭크", outcome="실험 종료", nickname="나"
    )

    assert "imagePath" not in match_result_dict(result)
    assert match_result_dict(result, image_path="x/r.jpg")["imagePath"] == "x/r.jpg"
