from datetime import datetime, timedelta, timezone

from lumia_briefing_room.api import backfill_routes as routes
from lumia_briefing_room.config import Config, PathsConfig
from lumia_briefing_room.pipeline.watcher import MatchBoundary, ProcessedState, match_key

T0 = datetime(2026, 9, 24, 6, 0, tzinfo=timezone.utc)


def match(hours, *, ended=True):
    start = T0 + timedelta(hours=hours)
    return MatchBoundary(start_utc=start, end_utc=start + timedelta(minutes=20) if ended else None)


def setup(tmp_path, monkeypatch, matches, processed):
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp"))
    monkeypatch.setattr("lumia_briefing_room.api.app.read_boundaries", lambda c: matches)
    ProcessedState(frozenset(match_key(m) for m in processed)).save(tmp_path / "tmp" / "processed_matches.json")
    return cfg


def test_log_games_the_watcher_will_still_make_are_known(tmp_path, monkeypatch):
    pending, running = match(1), match(2, ended=False)
    cfg = setup(tmp_path, monkeypatch, [pending, running], processed=[])
    assert routes.collect_log_starts(cfg) == [pending.start_utc, running.start_utc]


def test_already_processed_games_are_not_treated_as_having_clips(tmp_path, monkeypatch):
    """처리 이력만 있고 현재 클립 폴더에는 클립이 없는 경기(클립 폴더를 바꾼 뒤)는 과거 녹화 분석이 만들어야 한다."""
    done, pending = match(1), match(2)
    cfg = setup(tmp_path, monkeypatch, [done, pending], processed=[done])
    assert routes.collect_log_starts(cfg) == [pending.start_utc]


def test_missing_processed_state_means_everything_is_pending(tmp_path, monkeypatch):
    m = match(1)
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp"))
    monkeypatch.setattr("lumia_briefing_room.api.app.read_boundaries", lambda c: [m])
    assert routes.collect_log_starts(cfg) == [m.start_utc]
