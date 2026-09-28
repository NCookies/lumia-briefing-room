from datetime import datetime, timedelta, timezone

from lumia_briefing_room.config import RetentionConfig
from lumia_briefing_room.pipeline.retention import is_protected, select_for_auto_clean

UTC = timezone.utc


def test_is_protected_pinned_clip():
    cfg = RetentionConfig(protect_pinned=True)
    assert is_protected({"pinned": True, "tags": []}, cfg) is True


def test_is_protected_by_tag():
    cfg = RetentionConfig(protect_tags=["death"])
    assert is_protected({"pinned": False, "tags": ["death"]}, cfg) is True


def test_is_protected_false_for_ordinary_clip():
    cfg = RetentionConfig(protect_pinned=True, protect_tags=["death"])
    assert is_protected({"pinned": False, "tags": ["kill"]}, cfg) is False


def test_is_protected_pin_protection_can_be_disabled():
    cfg = RetentionConfig(protect_pinned=False)
    assert is_protected({"pinned": True, "tags": []}, cfg) is False


def _meta(clip_id, *, age_days, size_mb=50, pinned=False, tags=("kill",)):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    created = now - timedelta(days=age_days)
    return {
        "_clip_id": clip_id,
        "_created_at": created,
        "_size_bytes": size_mb * 1024 * 1024,
        "pinned": pinned,
        "tags": list(tags),
    }


def test_select_for_auto_clean_by_max_age():
    metas = [_meta("a", age_days=40), _meta("b", age_days=5)]
    cfg = RetentionConfig(auto_clean_enabled=True, max_age_days=30)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    selected = select_for_auto_clean(metas, cfg, now=lambda: now)
    assert [m["_clip_id"] for m in selected] == ["a"]


def test_select_for_auto_clean_respects_protection():
    metas = [_meta("a", age_days=40, pinned=True), _meta("b", age_days=40)]
    cfg = RetentionConfig(auto_clean_enabled=True, max_age_days=30, protect_pinned=True)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    selected = select_for_auto_clean(metas, cfg, now=lambda: now)
    assert [m["_clip_id"] for m in selected] == ["b"]


def test_select_for_auto_clean_by_max_total_gb_picks_oldest_first():
    metas = [
        _meta("oldest", age_days=30, size_mb=600),
        _meta("middle", age_days=20, size_mb=600),
        _meta("newest", age_days=10, size_mb=600),
    ]
    cfg = RetentionConfig(auto_clean_enabled=True, max_total_gb=1.0)  # 1GB = ~1024MB
    now = datetime(2026, 1, 1, tzinfo=UTC)
    selected = select_for_auto_clean(metas, cfg, now=lambda: now)
    # 총 1800MB 중 1024MB 를 넘는 776MB 만큼, 오래된 것부터 제거해야 함
    assert [m["_clip_id"] for m in selected] == ["oldest", "middle"]


def test_select_for_auto_clean_by_max_count():
    metas = [_meta(str(i), age_days=i) for i in range(5)]
    cfg = RetentionConfig(auto_clean_enabled=True, max_count=3)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    selected = select_for_auto_clean(metas, cfg, now=lambda: now)
    assert {m["_clip_id"] for m in selected} == {"3", "4"}


def test_select_for_auto_clean_disabled_returns_nothing():
    metas = [_meta("a", age_days=999)]
    cfg = RetentionConfig(auto_clean_enabled=False, max_age_days=1)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert select_for_auto_clean(metas, cfg, now=lambda: now) == []


def test_select_for_auto_clean_no_limits_set_returns_nothing():
    metas = [_meta("a", age_days=999)]
    cfg = RetentionConfig(auto_clean_enabled=True)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert select_for_auto_clean(metas, cfg, now=lambda: now) == []
