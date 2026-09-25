import json
from pathlib import Path

from lumia_briefing_room.config import (
    ClipConfig,
    Config,
    FilterConfig,
    PathsConfig,
    dataclass_from_camel_dict,
    dataclass_to_camel_dict,
    load_config,
    resolve_paths,
    save_config,
)


def test_default_config_matches_spec_defaults():
    cfg = Config()
    assert cfg.watch.poll_interval_ms == 1000
    assert cfg.watch.trigger_on == "lobby_return"
    assert cfg.watch.buffer_minutes == "auto"
    assert cfg.filter.preset == "all"
    assert cfg.filter.min_duration_sec == 4
    assert cfg.clip.preroll_sec == 5
    assert cfg.clip.postroll_sec == 8
    assert not hasattr(cfg.clip, "max_duration_sec")
    assert cfg.encode.proxy.enabled is False
    assert cfg.encode.thumbnail.enabled is True
    assert cfg.retention.delete_mode == "trash"
    assert cfg.retention.trash_days == 30
    assert cfg.retention.protect_tags == []
    assert cfg.ui.auto_start is True


def test_to_camel_dict_uses_spec_key_names():
    cfg = Config()
    d = dataclass_to_camel_dict(cfg)
    assert d["watch"]["pollIntervalMs"] == 1000
    assert d["filter"]["minDurationSec"] == 4
    assert d["clip"]["prerollSec"] == 5
    assert d["retention"]["trashDays"] == 30
    assert d["retention"]["protectTags"] == []


def test_path_fields_serialize_as_strings():
    cfg = Config(paths=PathsConfig(temp=Path("D:/scratch")))
    d = dataclass_to_camel_dict(cfg)
    assert d["paths"]["temp"] == "D:\\scratch" or d["paths"]["temp"] == "D:/scratch"


def test_none_path_serializes_as_none():
    cfg = Config()
    d = dataclass_to_camel_dict(cfg)
    assert d["paths"]["temp"] is None


def test_roundtrip_via_camel_dict():
    cfg = Config(
        filter=FilterConfig(preset="lost", min_duration_sec=6.0),
        clip=ClipConfig(preroll_sec=10.0),
        paths=PathsConfig(temp=Path("D:/scratch")),
    )
    d = dataclass_to_camel_dict(cfg)
    restored = dataclass_from_camel_dict(Config, d)

    assert restored.filter.preset == "lost"
    assert restored.filter.min_duration_sec == 6.0
    assert restored.clip.preroll_sec == 10.0
    assert restored.paths.temp == Path("D:/scratch")


def test_save_and_load_config_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config(filter=FilterConfig(preset="won"))

    save_config(cfg, path)
    loaded = load_config(path)

    assert loaded.filter.preset == "won"
    assert loaded.clip.preroll_sec == 5  # 건드리지 않은 기본값 유지


def test_load_config_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "does_not_exist.json")
    assert cfg == Config()


def test_load_config_with_partial_json_keeps_other_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"filter": {"preset": "lost"}}), encoding="utf-8")

    cfg = load_config(path)

    assert cfg.filter.preset == "lost"
    assert cfg.filter.min_duration_sec == 4  # 명시 안 한 필드는 기본값
    assert cfg.clip.preroll_sec == 5  # 다른 섹션도 그대로


def test_resolve_paths_fills_defaults_when_unset():
    resolved = resolve_paths(PathsConfig())
    assert resolved.clips.name == "clips"
    assert resolved.thumbnails == resolved.clips / ".thumbs"
    assert resolved.proxies == resolved.clips / ".proxy"
    assert resolved.trash == resolved.clips / ".trash"


def test_resolve_paths_respects_explicit_clips_dir():
    cfg = PathsConfig(clips=Path("E:/my_clips"))
    resolved = resolve_paths(cfg)
    assert resolved.clips == Path("E:/my_clips")
    assert resolved.thumbnails == Path("E:/my_clips/.thumbs")


def test_resolve_paths_respects_explicit_temp_dir():
    cfg = PathsConfig(temp=Path("D:/fast_scratch"))
    resolved = resolve_paths(cfg)
    assert resolved.temp == Path("D:/fast_scratch")


def test_vod_clips_path_defaults_next_to_steam_clips_and_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    default = resolve_paths(PathsConfig())
    custom = resolve_paths(PathsConfig(vod_clips=Path("D:/vod-out")))

    assert default.vod_clips == tmp_path / "Videos" / "LumiaBriefingRoom" / "vod"
    assert default.vod_clips != default.clips
    assert custom.vod_clips == Path("D:/vod-out")


def test_vod_config_defaults_are_safe():
    from lumia_briefing_room.config import VodConfig

    vod = Config().vod
    assert isinstance(vod, VodConfig)
    assert vod.sources == []
    assert vod.recursive is False
    assert vod.auto_analyze is False
    assert vod.game_gap_sec == 30.0
    assert vod.min_game_sec == 60.0
    assert vod.hwaccel is None
    assert vod.streamers == {}


def test_vod_config_round_trips_through_camel_json(tmp_path):
    cfg = Config()
    cfg.vod.sources = ["H:/vod", "H:/other.mp4"]
    cfg.vod.streamers = {"3fa91c02b7de": "○○○"}
    cfg.paths.vod_clips = Path("D:/vod-out")
    path = tmp_path / "config.json"

    save_config(cfg, path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    loaded = load_config(path)

    assert raw["vod"]["sources"] == ["H:/vod", "H:/other.mp4"]
    assert raw["vod"]["gameGapSec"] == 30.0
    assert Path(raw["paths"]["vodClips"]) == Path("D:/vod-out")
    assert loaded.vod.sources == ["H:/vod", "H:/other.mp4"]
    assert loaded.vod.streamers == {"3fa91c02b7de": "○○○"}
    assert loaded.paths.vod_clips == Path("D:/vod-out")


def test_resolve_config_path_falls_back_to_the_default_file(tmp_path):
    from lumia_briefing_room.config import DEFAULT_CONFIG_PATH, resolve_config_path

    assert resolve_config_path(None) == DEFAULT_CONFIG_PATH
    assert resolve_config_path(tmp_path / "x.json") == tmp_path / "x.json"


def test_discover_ffmpeg_prefers_env_then_bundle_then_path(tmp_path, monkeypatch):
    from lumia_briefing_room.config import discover_ffmpeg

    resource = tmp_path / "res"
    bundled = resource / "vendor" / "ffmpeg"
    bundled.mkdir(parents=True)
    (bundled / "ffmpeg.exe").write_bytes(b"")
    env_exe = tmp_path / "env_ffmpeg.exe"
    env_exe.write_bytes(b"")
    monkeypatch.setenv("LUMIA_RESOURCE_DIR", str(resource))
    monkeypatch.setattr("shutil.which", lambda name: "C:/path/ffmpeg.exe")

    monkeypatch.setenv("LUMIA_FFMPEG", str(env_exe))
    assert discover_ffmpeg() == env_exe

    monkeypatch.delenv("LUMIA_FFMPEG")
    assert discover_ffmpeg() == bundled / "ffmpeg.exe"

    (bundled / "ffmpeg.exe").unlink()
    assert discover_ffmpeg() == Path("C:/path/ffmpeg.exe")
