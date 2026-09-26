import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig, dataclass_from_camel_dict
from lumia_briefing_room.pipeline import proxy as proxy_module
from lumia_briefing_room.telemetry import environment
from lumia_briefing_room.telemetry import runtime_stats as rs
from lumia_briefing_room.telemetry.runtime_stats import RuntimeStats

CONTRACT = Path(__file__).resolve().parents[1] / "contract"
SCHEMA = json.loads((CONTRACT / "receiver.schema.json").read_text(encoding="utf-8"))


def test_empty_stats_report_nothing(tmp_path):
    assert RuntimeStats(tmp_path / "s.json").snapshot() == {}


def test_proxy_records_the_latest_encoder_and_the_recent_average_time(tmp_path):
    stats = RuntimeStats(tmp_path / "s.json")
    stats.record_proxy("h264_mf", 10.0)
    stats.record_proxy("libx264", 20.0)
    snap = stats.snapshot()
    assert snap["proxyEncoder"] == "libx264" and snap["proxyBuildSec"] == 15.0


def test_analysis_ratio_is_processing_time_over_game_length_averaged_over_recent_games(tmp_path):
    stats = RuntimeStats(tmp_path / "s.json")
    stats.record_analysis(process_sec=300, game_sec=1200, hwaccel=False)
    stats.record_analysis(process_sec=600, game_sec=1200, hwaccel=True)
    snap = stats.snapshot()
    assert snap["analysisTimeRatio"] == 0.375 and snap["hwaccel"] is True


def test_only_the_most_recent_samples_count(tmp_path):
    stats = RuntimeStats(tmp_path / "s.json")
    for _ in range(50):
        stats.record_proxy("h264_mf", 100.0)
    for _ in range(rs.WINDOW):
        stats.record_proxy("h264_mf", 10.0)
    assert stats.snapshot()["proxyBuildSec"] == 10.0


@pytest.mark.parametrize("seconds", [-1, 0, float("nan"), float("inf"), "x", None, True])
def test_nonsense_durations_are_ignored(tmp_path, seconds):
    stats = RuntimeStats(tmp_path / "s.json")
    stats.record_proxy("h264_mf", seconds)
    stats.record_analysis(process_sec=seconds, game_sec=100, hwaccel=False)
    stats.record_analysis(process_sec=10, game_sec=seconds, hwaccel=False)
    assert "proxyBuildSec" not in stats.snapshot() and "analysisTimeRatio" not in stats.snapshot()


def test_hevc_capability_is_recorded_as_reported(tmp_path):
    stats = RuntimeStats(tmp_path / "s.json")
    stats.record_hevc(False)
    assert stats.snapshot()["hevcPlayable"] is False
    stats.record_hevc(True)
    assert stats.snapshot()["hevcPlayable"] is True


def test_stats_survive_a_restart_and_a_corrupt_file_starts_fresh(tmp_path):
    path = tmp_path / "s.json"
    RuntimeStats(path).record_proxy("h264_mf", 12.0)
    assert RuntimeStats(path).snapshot()["proxyBuildSec"] == 12.0
    path.write_text("{broken", encoding="utf-8")
    assert RuntimeStats(path).snapshot() == {}


def test_recording_never_raises_even_if_the_path_is_unwritable(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    stats = RuntimeStats(blocker / "sub" / "s.json")
    stats.record_proxy("h264_mf", 1.0)
    stats.record_analysis(process_sec=1, game_sec=10, hwaccel=False)
    stats.record_hevc(True)


def test_module_helpers_swallow_every_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no")

    monkeypatch.setattr(rs, "get_runtime_stats", boom)
    rs.record_proxy("x", 1.0)
    rs.record_analysis(1, 10, False)
    rs.record_hevc(True)


# ── 환경 정보에 실리는지 ───────────────────────────────────────────


def test_environment_includes_the_recorded_runtime_values_and_satisfies_the_contract(tmp_path, monkeypatch):
    stats = RuntimeStats(tmp_path / "s.json")
    stats.record_proxy("h264_mf", 12.34)
    stats.record_analysis(process_sec=300, game_sec=1200, hwaccel=True)
    stats.record_hevc(False)
    monkeypatch.setattr(rs, "get_runtime_stats", lambda: stats)
    cfg = dataclass_from_camel_dict(Config, {"paths": {"clips": str(tmp_path / "c"), "vodClips": str(tmp_path / "v")}})
    env = environment.collect_environment(cfg)
    assert env["proxyEncoder"] == "h264_mf" and env["proxyBuildSec"] == 12.3
    assert env["analysisTimeRatio"] == 0.25 and env["hwaccel"] is True and env["hevcPlayable"] is False
    validator = Draft202012Validator({"$ref": "#/$defs/Environment", "$defs": SCHEMA["$defs"]})
    assert list(validator.iter_errors(env)) == []


def test_hwaccel_falls_back_to_the_vod_setting_when_no_analysis_was_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "get_runtime_stats", lambda: RuntimeStats(tmp_path / "empty.json"))
    on = dataclass_from_camel_dict(Config, {"vod": {"hwaccel": "d3d11va"}, "paths": {"clips": str(tmp_path / "c")}})
    off = dataclass_from_camel_dict(Config, {"paths": {"clips": str(tmp_path / "c")}})
    assert environment.collect_environment(on)["hwaccel"] is True
    assert environment.collect_environment(off)["hwaccel"] is False


# ── 계측 지점 ────────────────────────────────────────────────────────


def test_create_proxy_records_the_encoder_and_the_time_it_took(tmp_path, monkeypatch):
    stats = RuntimeStats(tmp_path / "s.json")
    monkeypatch.setattr(rs, "get_runtime_stats", lambda: stats)
    monkeypatch.setattr(proxy_module, "list_encoders", lambda ffmpeg: ["h264_mf", "libx264"])
    monkeypatch.setattr(proxy_module, "_run_encode", lambda cmd, duration, on_progress: Path(cmd[-1]).write_bytes(b"x"))
    ticks = iter([100.0, 107.5])
    monkeypatch.setattr(proxy_module.time, "monotonic", lambda: next(ticks))
    used = proxy_module.create_proxy(Path("ffmpeg"), Path("in.mp4"), tmp_path / "out" / "p.mp4", height=1080, crf=23, duration_sec=30)
    assert used == "h264_mf"
    assert stats.snapshot()["proxyEncoder"] == "h264_mf" and stats.snapshot()["proxyBuildSec"] == 7.5


def test_a_failed_proxy_build_is_not_recorded(tmp_path, monkeypatch):
    stats = RuntimeStats(tmp_path / "s.json")
    monkeypatch.setattr(rs, "get_runtime_stats", lambda: stats)
    monkeypatch.setattr(proxy_module, "list_encoders", lambda ffmpeg: ["libx264"])

    def fail(cmd, duration, on_progress):
        raise proxy_module.ProxyError("nope")

    monkeypatch.setattr(proxy_module, "_run_encode", fail)
    with pytest.raises(proxy_module.ProxyError):
        proxy_module.create_proxy(Path("ffmpeg"), Path("in.mp4"), tmp_path / "p.mp4", height=1080, crf=23, duration_sec=30)
    assert stats.snapshot() == {}


def test_watch_processor_records_analysis_time_against_game_length(tmp_path, monkeypatch):
    from lumia_briefing_room.cli import watch
    from lumia_briefing_room.pipeline.playerlog import MatchBoundary

    stats = RuntimeStats(tmp_path / "s.json")
    monkeypatch.setattr(rs, "get_runtime_stats", lambda: stats)
    monkeypatch.setattr(watch.RecordingSession, "load", staticmethod(lambda d: MagicMock()))
    ticks = iter([1000.0, 1300.0])
    monkeypatch.setattr(watch.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(watch, "process_match", lambda *a, **k: [])
    start = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    end = datetime(2026, 9, 25, 12, 20, tzinfo=timezone.utc)
    process = watch.make_processor(Config(paths=PathsConfig(temp=tmp_path)), Path("ffmpeg"), game_mode="battle_royale",
                                   k_templates=None, a_templates=None, hwaccel="d3d11va")
    process(tmp_path, MatchBoundary(start_utc=start, end_utc=end), False)
    assert stats.snapshot()["analysisTimeRatio"] == 0.25 and stats.snapshot()["hwaccel"] is True


# ── 브라우저가 알려 주는 HEVC 재생 가능 여부 ────────────────────────


def test_client_capabilities_endpoint_stores_hevc_support(tmp_path, monkeypatch):
    stats = RuntimeStats(tmp_path / "s.json")
    monkeypatch.setattr(rs, "get_runtime_stats", lambda: stats)
    app = create_app(Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "t")), config_path=tmp_path / "config.json")
    client = TestClient(app)
    assert client.post("/api/client-capabilities", json={"hevcPlayable": False}).status_code == 200
    assert stats.snapshot()["hevcPlayable"] is False
    assert client.post("/api/client-capabilities", json={"hevcPlayable": "maybe"}).status_code == 400
    assert client.post("/api/client-capabilities", json={}).status_code == 400
