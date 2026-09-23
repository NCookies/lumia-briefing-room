import dataclasses
import json
import os
import shutil
import types
import typing
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BUNDLED_FFMPEG = _PROJECT_ROOT / "vendor" / "ffmpeg" / "ffmpeg.exe"

FFMPEG_NOT_FOUND_MESSAGE = (
    "ffmpeg를 찾을 수 없다. 'winget install ffmpeg' 로 설치하거나, "
    "--ffmpeg 옵션 또는 LUMIA_FFMPEG 환경변수로 ffmpeg.exe 경로를 직접 지정할 것."
)


def discover_ffmpeg() -> Path | None:
    """ffmpeg 실행 파일을 찾는다.

    SPEC §4: ffmpeg 번들이 필수다. 우선순위:
      1) LUMIA_FFMPEG 환경변수
      2) 번들된 위치 (vendor/ffmpeg/ffmpeg.exe)
      3) PATH
    """
    env_path = os.environ.get("LUMIA_FFMPEG")
    if env_path and Path(env_path).exists():
        return Path(env_path)

    if _BUNDLED_FFMPEG.exists():
        return _BUNDLED_FFMPEG

    found = shutil.which("ffmpeg")
    return Path(found) if found else None


# ── 설정 스키마 (SPEC §7) ──────────────────────────────────────────────
#
# 파이썬 필드는 snake_case, 설정 파일(config.json)은 SPEC §7 표 그대로
# camelCase 점 표기다. dataclass_to_camel_dict/dataclass_from_camel_dict 가 변환한다.


@dataclass
class PathsConfig:
    temp: Path | None = None
    clips: Path | None = None
    thumbnails: Path | None = None
    proxies: Path | None = None
    trash: Path | None = None
    export_default: Path | None = None
    steam_recording: Path | None = None
    vod_clips: Path | None = None
    min_free_gb: float = 20.0


@dataclass
class ResolvedPaths:
    temp: Path
    clips: Path
    thumbnails: Path
    proxies: Path
    trash: Path
    export_default: Path
    vod_clips: Path


def _default_local_appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))


def _default_appdata() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))


def _default_userprofile() -> Path:
    return Path(os.environ.get("USERPROFILE", str(Path.home())))


def resolve_paths(cfg: PathsConfig) -> ResolvedPaths:
    """SPEC §7.1: 비워두면 기본 위치, thumbnails/proxies/trash 는 clips 하위."""
    clips = cfg.clips or (_default_userprofile() / "Videos" / "LumiaBriefingRoom" / "clips")
    return ResolvedPaths(
        temp=cfg.temp or (_default_local_appdata() / "Temp" / "LumiaBriefingRoom"),
        clips=clips,
        thumbnails=cfg.thumbnails or (clips / ".thumbs"),
        proxies=cfg.proxies or (clips / ".proxy"),
        trash=cfg.trash or (clips / ".trash"),
        export_default=cfg.export_default or (_default_userprofile() / "Videos"),
        vod_clips=cfg.vod_clips or (_default_userprofile() / "Videos" / "LumiaBriefingRoom" / "vod"),
    )


@dataclass
class WatchConfig:
    player_log: Path | None = None
    poll_interval_ms: int = 1000
    trigger_on: str = "lobby_return"
    delay_sec: float = 5.0
    buffer_minutes: str | float = "auto"
    process_backlog: bool = True
    rescue_threshold_min: float = 20.0
    retry_count: int = 3


@dataclass
class TagFilter:
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


@dataclass
class FilterConfig:
    preset: str = "all"
    tags: TagFilter = field(default_factory=TagFilter)
    phase_min: int | None = None
    phase_max: int | None = None
    day_night: str = "any"
    revive_cost: str = "any"
    min_duration_sec: float = 4.0
    max_duration_sec: float | None = None
    game_mode: str = "any"
    my_character: list[str] = field(default_factory=list)
    min_pvp_score: float = 0.0
    pvp_weights: dict[str, float] = field(
        default_factory=lambda: {
            "enemyRings": 0.0, "death": 0.9, "teammateDeath": 0.8, "teammateDeathSplit": 0.5, "ultimateUsed": 0.6,
        }
    )


@dataclass
class ClipConfig:
    mode: str = "combat"
    preroll_sec: float = 5.0
    postroll_sec: float = 8.0
    fixed_preroll_sec: float = 30.0
    max_duration_sec: float = 90.0
    merge_gap_sec: float = 10.0
    include_audio: bool = True
    snap_to_keyframe: bool = True


@dataclass
class ThumbnailConfig:
    enabled: bool = True
    offset_ratio: float = 0.35
    width: int = 480


@dataclass
class ProxyConfig:
    enabled: bool = False
    height: int = 1080
    crf: int = 23


@dataclass
class EncodeConfig:
    reencode: bool = False
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    thumbnail: ThumbnailConfig = field(default_factory=ThumbnailConfig)


@dataclass
class RetentionConfig:
    delete_mode: str = "trash"
    trash_days: int = 30
    auto_clean_enabled: bool = False
    max_age_days: int | None = None
    max_total_gb: float | None = None
    max_count: int | None = None
    protect_pinned: bool = True
    protect_tags: list[str] = field(default_factory=lambda: ["death"])
    keep_game_records: bool = True


@dataclass
class ExportConfig:
    copy_metadata: bool = True
    copy_thumbnail: bool = True
    mode: str = "copy"
    name_template: str = "{date}_{title}"


@dataclass
class UiConfig:
    shell: str = "webview"
    port: str | int = 8765
    default_view: str = "timeline"
    title_template: str = "{day}일차 {dayNight} {myChar}, {teamChars}"
    language: str = "ko"
    theme: str = "dark"
    start_minimized: bool = True
    auto_start: bool = True
    confirm_delete: bool = True


@dataclass
class PlayerConfig:
    nickname: str = ""


@dataclass
class VodConfig:
    sources: list[str] = field(default_factory=list)
    recursive: bool = False
    auto_analyze: bool = False
    game_gap_sec: float = 30.0
    min_game_sec: float = 60.0
    hwaccel: str | None = None
    streamers: dict[str, str] = field(default_factory=dict)


@dataclass
class Config:
    paths: PathsConfig = field(default_factory=PathsConfig)
    watch: WatchConfig = field(default_factory=WatchConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    clip: ClipConfig = field(default_factory=ClipConfig)
    encode: EncodeConfig = field(default_factory=EncodeConfig)
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    player: PlayerConfig = field(default_factory=PlayerConfig)
    vod: VodConfig = field(default_factory=VodConfig)


DEFAULT_CONFIG_PATH = _default_appdata() / "LumiaBriefingRoom" / "config.json"


# ── camelCase JSON 직렬화 ──────────────────────────────────────────────


def _to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p.capitalize() for p in rest)


def _encode_value(value):
    if dataclasses.is_dataclass(value):
        return dataclass_to_camel_dict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_encode_value(v) for v in value]
    return value


def dataclass_to_camel_dict(obj) -> dict:
    return {_to_camel(f.name): _encode_value(getattr(obj, f.name)) for f in dataclasses.fields(obj)}


def _unwrap_optional(tp):
    origin = typing.get_origin(tp)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        if args:
            return args[0]
    return tp


def _decode_value(value, tp):
    if value is None:
        return None
    tp = _unwrap_optional(tp)
    if dataclasses.is_dataclass(tp):
        return dataclass_from_camel_dict(tp, value)
    if tp is Path:
        return Path(value)
    if typing.get_origin(tp) is list:
        return list(value)
    return value


def dataclass_from_camel_dict(cls, data: dict):
    hints = typing.get_type_hints(cls)
    kwargs = {}
    for f in dataclasses.fields(cls):
        camel = _to_camel(f.name)
        if camel not in data:
            continue
        kwargs[f.name] = _decode_value(data[camel], hints[f.name])
    return cls(**kwargs)


def resolve_config_path(path: Path | None) -> Path:
    """설정 파일 경로. 지정하지 않으면 기본 파일이다. 읽을 때만이 아니라 저장할 때도 같은 파일이어야 한다."""
    return path or DEFAULT_CONFIG_PATH


def load_config(path: Path | None = None) -> Config:
    path = path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return Config()
    data = json.loads(path.read_text(encoding="utf-8"))
    return dataclass_from_camel_dict(Config, data)


def save_config(cfg: Config, path: Path | None = None) -> None:
    path = path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(dataclass_to_camel_dict(cfg), ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
