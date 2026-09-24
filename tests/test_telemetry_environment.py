import json
from pathlib import Path

from jsonschema import Draft202012Validator

from lumia_briefing_room import __version__
from lumia_briefing_room.config import Config, dataclass_from_camel_dict
from lumia_briefing_room.telemetry import endpoint as endpoint_module
from lumia_briefing_room.telemetry import environment
from lumia_briefing_room.telemetry.endpoint import DEFAULT_SERVER_URL, load_endpoint
from lumia_briefing_room.telemetry.state import TelemetryState

CONTRACT = Path(__file__).resolve().parent / "contract"
SCHEMA = json.loads((CONTRACT / "receiver.schema.json").read_text(encoding="utf-8"))


def cfg(**telemetry):
    return dataclass_from_camel_dict(Config, {"telemetry": telemetry})


def test_config_token_wins_over_environment_and_bundle(monkeypatch):
    monkeypatch.setattr(endpoint_module, "bundled_endpoint", lambda: {"token": "bundled", "url": "https://b.example"})
    found = load_endpoint(cfg(apiToken="cfg", serverUrl="https://c.example/"), environ={"LUMIA_RECEIVER_TOKEN": "env"})
    assert found.token == "cfg" and found.url == "https://c.example"


def test_environment_then_bundle_then_default_url(monkeypatch):
    monkeypatch.setattr(endpoint_module, "bundled_endpoint", lambda: {"token": "bundled"})
    assert load_endpoint(cfg(), environ={"LUMIA_RECEIVER_TOKEN": "env"}).token == "env"
    found = load_endpoint(cfg(), environ={})
    assert found.token == "bundled" and found.url == DEFAULT_SERVER_URL
    assert load_endpoint(cfg(), environ={"LUMIA_RECEIVER_URL": "https://e.example"}).url == "https://e.example"


def test_no_token_anywhere_means_no_endpoint(monkeypatch):
    monkeypatch.setattr(endpoint_module, "bundled_endpoint", lambda: {})
    assert load_endpoint(cfg(), environ={}) is None
    assert load_endpoint(cfg(apiToken="   "), environ={}) is None


def test_bundled_endpoint_reads_the_data_file_and_tolerates_absence(tmp_path, monkeypatch):
    monkeypatch.setattr(endpoint_module.paths, "data_dir", lambda: tmp_path)
    assert endpoint_module.bundled_endpoint() == {}
    (tmp_path / "telemetry_endpoint.json").write_text('{"token": "t", "url": "https://x"}', encoding="utf-8")
    assert endpoint_module.bundled_endpoint() == {"token": "t", "url": "https://x"}
    (tmp_path / "telemetry_endpoint.json").write_text("not json", encoding="utf-8")
    assert endpoint_module.bundled_endpoint() == {}


def test_state_survives_reload_and_recovers_from_a_corrupt_file(tmp_path):
    path = tmp_path / "state.json"
    state = TelemetryState(path)
    state.update("labels", failures=2, nextAttempt=99.0)
    state.remember({"k": "d"})
    reloaded = TelemetryState(path)
    assert reloaded.kind("labels")["failures"] == 2 and reloaded.digests() == {"k": "d"}
    path.write_text("{broken", encoding="utf-8")
    assert TelemetryState(path).kind("labels")["failures"] == 0 and TelemetryState(path).digests() == {}
    reloaded.reset()
    assert reloaded.digests() == {} and reloaded.kind("logs")["nextAttempt"] == 0.0


def test_read_fail_stats_counts_clips_missing_readings(tmp_path):
    clips, vod = tmp_path / "clips", tmp_path / "vod"
    clips.mkdir()
    vod.mkdir()
    full = {"matchResult": {"placement": 1}, "myCharacter": "아야", "region": "학교", "gameDay": 1, "matchKills": 2}
    (clips / "a.json").write_text(json.dumps(full), encoding="utf-8")
    (clips / "b.json").write_text(json.dumps({"sourceIncomplete": True}), encoding="utf-8")
    (vod / "c.json").write_text(json.dumps({"region": "숲"}), encoding="utf-8")
    trash = clips / ".trash"
    trash.mkdir()
    (trash / "t.json").write_text("{}", encoding="utf-8")
    config = dataclass_from_camel_dict(Config, {"paths": {"clips": str(clips), "vodClips": str(vod)}})
    stats = environment.read_fail_stats(config)
    assert stats == {"clips_total": 3, "no_match_result": 2, "no_my_character": 2, "no_region": 1, "no_game_day": 2,
                     "no_match_kills": 2, "source_incomplete": 1}


def test_collected_environment_satisfies_the_contract_on_this_machine(tmp_path):
    config = dataclass_from_camel_dict(Config, {"paths": {"clips": str(tmp_path / "c"), "vodClips": str(tmp_path / "v")}})
    env = environment.collect_environment(config)
    validator = Draft202012Validator({"$ref": "#/$defs/Environment", "$defs": SCHEMA["$defs"]})
    assert list(validator.iter_errors(env)) == []
    assert env["appVersion"] == __version__ and env["os"]


def test_environment_never_raises_when_probes_fail(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("no")

    for name in ("_cpu_model", "_gpu_name", "_memory_mb", "_display_scale", "_ffmpeg_build", "_locale_name"):
        monkeypatch.setattr(environment, name, boom)
    monkeypatch.setattr(environment, "_recording", boom)
    config = dataclass_from_camel_dict(Config, {"paths": {"clips": str(tmp_path / "c"), "vodClips": str(tmp_path / "v")}})
    try:
        env = environment.collect_environment(config)
    except RuntimeError:
        raise AssertionError("환경 정보 수집이 예외를 밖으로 냈다")
    assert env["appVersion"]
