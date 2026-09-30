import dataclasses
import json
import os
import shutil
import types
import typing
from dataclasses import dataclass, field
from pathlib import Path

from lumia_briefing_room import paths


FFMPEG_NOT_FOUND_MESSAGE = (
    "ffmpeg를 찾을 수 없습니다. 'winget install ffmpeg'로 설치하거나, "
    "--ffmpeg 옵션 또는 LUMIA_FFMPEG 환경변수로 ffmpeg.exe 경로를 직접 지정해 주세요."
)


def discover_ffmpeg() -> Path | None:
    """ffmpeg 실행 파일을 찾는다.

    SPEC §4: ffmpeg 번들이 필수다. 우선순위:
      1) LUMIA_FFMPEG 환경변수
      2) 번들된 위치 (paths.bundled_ffmpeg_dir())
      3) PATH
    """
    env_path = os.environ.get("LUMIA_FFMPEG")
    if env_path and Path(env_path).exists():
        return Path(env_path)

    bundled = paths.bundled_ffmpeg_dir() / "ffmpeg.exe"
    if bundled.exists():
        return bundled

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
    export_default: Path | None = None
    steam_recording: Path | None = None
    vod_clips: Path | None = None
    games: Path | None = None
    root: Path | None = None
    full_videos: Path | None = None
    min_free_gb: float = 20.0


@dataclass
class ResolvedPaths:
    temp: Path
    clips: Path
    export_default: Path
    vod_clips: Path
    games: Path
    clips_steam: Path
    clips_vod: Path
    clips_root: Path
    clip_roots: tuple[Path, ...]
    games_steam: Path
    games_vod: Path
    library_steam: Path
    library_vod: Path
    staging_clips: Path
    staging_games: Path
    staging_library_steam: Path
    staging_library_vod: Path
    staging_vod_clips: Path
    proxy_cache: Path

    @property
    def games_dirs(self) -> tuple[Path, ...]:
        """풀영상 폴더 전부(스팀·영상 파일). 옛 경로 모드에선 같은 폴더라 하나."""
        return tuple(dict.fromkeys((self.games_steam, self.games_vod)))


def _default_local_appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))


def _default_appdata() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))


def _default_userprofile() -> Path:
    return Path(os.environ.get("USERPROFILE", str(Path.home())))


CLIPS_FOLDER = "clips"
FULL_VIDEOS_FOLDER = "full_video"
STEAM_FOLDER = "steam_replay"
VOD_FOLDER = "vod"
ARCHIVE_FOLDER = "보관함"
AUTO_ARCHIVE_FOLDER = "자동 보관"
STAGING_FOLDER = ".staging"


def uses_legacy_layout(cfg: PathsConfig) -> bool:
    """`paths.root` 가 없으면 옛 경로(clips·vodClips·games)를 그대로 인정한다."""
    return cfg.root is None


def _default_storage_root() -> Path:
    return _default_userprofile() / "Videos" / paths.app_folder_name()


def suggested_root(cfg: PathsConfig) -> Path | None:
    """첫 실행에서 저장 폴더로 권하는 기본값. 옛 경로를 이미 쓰는 사용자(설정 키 또는 옛 기본 폴더)에겐 None."""
    if cfg.root is not None or cfg.clips or cfg.vod_clips or cfg.games:
        return None
    if (_default_storage_root() / "clips").exists():
        return None
    return _default_storage_root()


def resolve_paths(cfg: PathsConfig) -> ResolvedPaths:
    """SPEC §7.1: 비워두면 기본 위치. 정보(json·썸네일 등)는 항상 앱 데이터 폴더, 영상만 저장 폴더(plan-fullvideo §3.10)."""
    library = _default_local_appdata() / paths.app_folder_name() / "library"
    temp = cfg.temp or (_default_local_appdata() / "Temp" / paths.app_folder_name())
    export_default = cfg.export_default or (_default_userprofile() / "Videos")
    common = dict(
        temp=temp,
        export_default=export_default,
        library_steam=library / "steam",
        library_vod=library / "vod",
        staging_library_steam=library / "steam" / STAGING_FOLDER,
        staging_library_vod=library / "vod" / STAGING_FOLDER,
    )
    if cfg.root is not None:
        root = cfg.root
        full = cfg.full_videos or (root / FULL_VIDEOS_FOLDER)
        clips_steam = clips_vod = root / CLIPS_FOLDER / AUTO_ARCHIVE_FOLDER
        proxy_cache = root / ".cache" / "proxy"
        return ResolvedPaths(
            clips=clips_steam,
            vod_clips=clips_vod,
            games=full / STEAM_FOLDER,
            clips_steam=clips_steam,
            clips_vod=clips_vod,
            clips_root=root / CLIPS_FOLDER,
            clip_roots=(root / CLIPS_FOLDER,),
            games_steam=full / STEAM_FOLDER,
            games_vod=full / VOD_FOLDER,
            staging_clips=root / STAGING_FOLDER,
            staging_vod_clips=root / STAGING_FOLDER,
            staging_games=full / STAGING_FOLDER,
            proxy_cache=proxy_cache,
            **common,
        )
    clips = cfg.clips or (_default_storage_root() / "clips")
    vod_clips = cfg.vod_clips or (_default_storage_root() / "vod")
    games = cfg.games or (clips.parent / "games")
    return ResolvedPaths(
        clips=clips,
        vod_clips=vod_clips,
        games=games,
        clips_steam=clips,
        clips_vod=vod_clips,
        clips_root=clips,
        clip_roots=(clips, vod_clips),
        games_steam=games,
        games_vod=games,
        staging_clips=clips / STAGING_FOLDER,
        staging_vod_clips=vod_clips / STAGING_FOLDER,
        staging_games=games / STAGING_FOLDER,
        proxy_cache=clips / ".proxy",
        **common,
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
            "enemyRings": 0.0, "death": 0.9, "teammateDeath": 0.8, "teammateDeathSplit": 0.5, "ultimateUsed": 0.75,
        }
    )


@dataclass
class ClipConfig:
    mode: str = "combat"
    preroll_sec: float = 5.0
    postroll_sec: float = 8.0
    fixed_preroll_sec: float = 30.0
    merge_gap_sec: float = 10.0
    include_audio: bool = True
    snap_to_keyframe: bool = True
    save_mode: str = "auto"


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
    prefetch: bool = True


@dataclass
class EncodeConfig:
    reencode: bool = False
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    thumbnail: ThumbnailConfig = field(default_factory=ThumbnailConfig)


@dataclass
class RetentionConfig:
    delete_mode: str = "permanent"
    auto_clean_enabled: bool = True
    max_age_days: int | None = None
    max_total_gb: float | None = 40.0
    max_count: int | None = None
    protect_pinned: bool = True
    protect_tags: list[str] = field(default_factory=list)
    keep_game_records: bool = True
    preserve_before_delete: bool = False


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
    delete_mode: str = "recycle"


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
    video_dates: dict[str, str] = field(default_factory=dict)  # vodId -> 사용자가 고친 날짜(YYYY-MM-DD), plan-vod.md V8
    delete_source_after: str = "ask"  # "ask" | "always" | "never", plan-vod.md V7
    delete_source_mode: str = "trash"  # "trash" | "permanent", plan-vod.md V7


@dataclass
class AppConfig:
    mode: str = "auto"
    low_priority: bool = True


@dataclass
class UpdateConfig:
    check: bool = False


@dataclass
class TelemetryConfig:
    send_labels: bool = False
    send_logs: bool = False
    install_id: str = ""
    server_url: str = ""
    api_token: str = ""
    allow_dev_send: bool = False


@dataclass
class ConsentConfig:
    version: int = 0


@dataclass
class Config:
    app: AppConfig = field(default_factory=AppConfig)
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
    update: UpdateConfig = field(default_factory=UpdateConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    consent: ConsentConfig = field(default_factory=ConsentConfig)


def default_config_path() -> Path:
    return _default_appdata() / paths.app_folder_name() / "config.json"


DEFAULT_CONFIG_PATH = default_config_path()


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
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return dataclass_from_camel_dict(Config, data)


def save_config(cfg: Config, path: Path | None = None) -> None:
    path = path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(dataclass_to_camel_dict(cfg), ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
