from lumia_briefing_room.api.clips import ClipSummary
from lumia_briefing_room.api.filters import ClipQuery, filter_clip_summaries
from pathlib import Path
from datetime import datetime, timezone


def cs(clip_id, **meta):
    return ClipSummary(
        id=clip_id, meta_path=Path(f"/fake/{clip_id}.json"),
        meta={"tags": [], "dayNight": None, "gameMode": "battle_royale",
              "pinned": False, "deletedAt": None, **meta},
        size_bytes=100, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_no_filter_returns_all():
    clips = [cs("a"), cs("b")]
    assert filter_clip_summaries(clips, ClipQuery()) == clips


def test_filter_by_tag():
    clips = [cs("a", tags=["kill"]), cs("b", tags=["death"])]
    result = filter_clip_summaries(clips, ClipQuery(tags=["death"]))
    assert [c.id for c in result] == ["b"]


def test_filter_by_multiple_tags_is_or():
    clips = [cs("a", tags=["kill"]), cs("b", tags=["death"]), cs("c", tags=["no_result"])]
    result = filter_clip_summaries(clips, ClipQuery(tags=["kill", "death"]))
    assert {c.id for c in result} == {"a", "b"}


def test_filter_by_day_night():
    clips = [cs("a", dayNight="day"), cs("b", dayNight="night")]
    result = filter_clip_summaries(clips, ClipQuery(day_night="night"))
    assert [c.id for c in result] == ["b"]


def test_filter_by_game_mode():
    clips = [cs("a", gameMode="battle_royale"), cs("b", gameMode="cobalt")]
    result = filter_clip_summaries(clips, ClipQuery(game_mode="cobalt"))
    assert [c.id for c in result] == ["b"]


def test_filter_pinned_only():
    clips = [cs("a", pinned=True), cs("b", pinned=False)]
    result = filter_clip_summaries(clips, ClipQuery(pinned_only=True))
    assert [c.id for c in result] == ["a"]


def test_filter_excludes_trashed_by_default():
    clips = [cs("a", deletedAt=None), cs("b", deletedAt="2026-01-01T00:00:00+00:00")]
    result = filter_clip_summaries(clips, ClipQuery())
    assert [c.id for c in result] == ["a"]


def test_filter_trashed_only():
    clips = [cs("a", deletedAt=None), cs("b", deletedAt="2026-01-01T00:00:00+00:00")]
    result = filter_clip_summaries(clips, ClipQuery(trashed_only=True))
    assert [c.id for c in result] == ["b"]


def test_combined_filters_are_and():
    clips = [
        cs("a", tags=["kill"], dayNight="day"),
        cs("b", tags=["kill"], dayNight="night"),
        cs("c", tags=["death"], dayNight="day"),
    ]
    result = filter_clip_summaries(clips, ClipQuery(tags=["kill"], day_night="day"))
    assert [c.id for c in result] == ["a"]
