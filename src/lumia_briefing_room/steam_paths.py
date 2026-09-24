"""스팀 설치 위치와 `localconfig.vdf` 를 읽어 녹화 경로/버퍼 설정을 자동으로 찾는다.

research.md §1.1, plan-pipeline.md §3-4: 배경 녹화 폴더(BackgroundRecordPath)와
게임별 버퍼 분(PerGameSettings.<appid>.minutes) 은 스팀 계정마다 하나씩 있는
`userdata\\<steamid>\\config\\localconfig.vdf` 안에 있다. 계정이 여러 개면 값이
실제로 설정된 계정을 찾아 써야 한다(연구 결과: 이 값을 설정 안 한 계정도 있었다).

이 모듈이 있으면 사용자가 녹화 폴더 경로를 직접 설정하지 않아도 된다 — 다른
사람이 이 프로그램을 쓸 때도 스팀 설치 위치만 있으면 자동으로 찾아진다.
"""

import re
import winreg
from pathlib import Path

_STEAM_REGISTRY_KEYS = (
    (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
)

_TOKEN_RE = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')


def find_steam_install_path() -> Path | None:
    """레지스트리에서 스팀 설치 경로를 찾는다. 없으면(스팀 미설치 등) None."""
    for hive, subkey, value_name in _STEAM_REGISTRY_KEYS:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
        except OSError:
            continue
        if value:
            return Path(value)
    return None


def _unescape(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append(s[i + 1])
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def parse_vdf(text: str) -> dict:
    """중첩 중괄호 기반의 Valve VDF 텍스트 포맷을 최소 파싱해 dict 로 돌려준다."""
    tokens = [
        _unescape(m.group(1)) if m.group(1) is not None else m.group(2)
        for m in _TOKEN_RE.finditer(text)
    ]

    def parse_block(pos: int) -> tuple[dict, int]:
        result: dict = {}
        while pos < len(tokens):
            tok = tokens[pos]
            if tok == "}":
                return result, pos + 1
            key = tok
            pos += 1
            if pos < len(tokens) and tokens[pos] == "{":
                value, pos = parse_block(pos + 1)
            else:
                value = tokens[pos]
                pos += 1
            result[key] = value
        return result, pos

    root, _ = parse_block(0)
    return root


def _find_all(node, key: str):
    if isinstance(node, dict):
        if key in node:
            yield node[key]
        for value in node.values():
            yield from _find_all(value, key)


def _each_game_recording_block(steam_path: Path):
    for vdf_path in sorted(steam_path.glob("userdata/*/config/localconfig.vdf")):
        try:
            data = parse_vdf(vdf_path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        for block in _find_all(data, "GameRecording"):
            if isinstance(block, dict):
                yield block


def read_background_record_path(steam_path: Path) -> Path | None:
    """계정들 중 `BackgroundRecordPath` 가 설정된 첫 값을 찾는다."""
    for block in _each_game_recording_block(steam_path):
        value = block.get("BackgroundRecordPath")
        if value:
            return Path(value)
    return None


def read_buffer_minutes_override(steam_path: Path, app_id: str) -> float | None:
    """`PerGameSettings.<app_id>.minutes` 값을 찾는다. 없으면 None."""
    for block in _each_game_recording_block(steam_path):
        per_game = block.get("PerGameSettings")
        if not isinstance(per_game, dict):
            continue
        game = per_game.get(app_id)
        if isinstance(game, dict) and game.get("minutes") is not None:
            return float(game["minutes"])
    return None


SESSION_FOLDER = re.compile(r"^bg_\d+_\d{8}_\d{6}$")


def _session_dirs(video_dir: Path) -> list[Path]:
    try:
        return [d for d in video_dir.iterdir() if d.is_dir() and SESSION_FOLDER.match(d.name)]
    except OSError:
        return []


def _default_video_dirs(steam_path: Path) -> list[Path]:
    """녹화 폴더를 바꾸지 않았을 때의 기본 위치 `userdata/<id>/gamerecordings/video`.

    폴더를 바꾸지 않으면 localconfig.vdf 에 `BackgroundRecordPath` 자체가 저장되지 않는다(친구 PC 실측 사례).
    계정이 여러 개면 녹화가 들어 있는 것, 그중에서도 가장 최근 세션이 있는 계정을 고른다.
    """
    found = []
    for video in sorted(steam_path.glob("userdata/*/gamerecordings/video")):
        if video.is_dir():
            sessions = _session_dirs(video)
            newest = max((d.stat().st_mtime for d in sessions), default=-1.0)
            found.append((bool(sessions), newest, video))
    found.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [video for _, _, video in found]


def discover_recording_root(steam_path: Path | None = None) -> Path | None:
    """스팀의 배경 녹화 저장 위치를 자동으로 찾는다.

    1) 사용자가 폴더를 바꿨다면 `<BackgroundRecordPath>/video`
    2) 안 바꿨다면 기본 위치 `userdata/<id>/gamerecordings/video`(녹화가 있는 계정 우선)
    스팀 설치를 못 찾거나 둘 다 없으면 None — 호출자가 직접 고르게 해야 한다.
    """
    steam_path = steam_path if steam_path is not None else find_steam_install_path()
    if steam_path is None:
        return None
    record_path = read_background_record_path(steam_path)
    if record_path is not None:
        return record_path / "video"
    defaults = _default_video_dirs(steam_path)
    return defaults[0] if defaults else None


def normalize_recording_root(root: Path | None) -> Path | None:
    """사용자가 직접 고른 폴더가 `gamerecordings`(한 단계 위)여도 `video` 로 바로잡는다.

    녹화 세션(bg_...)이 이미 들어 있으면 그대로 두고, 없을 때만 `video` 하위 폴더를 본다.
    """
    if root is None:
        return None
    root = Path(root)
    if _session_dirs(root):
        return root
    child = root / "video"
    if child.is_dir() and _session_dirs(child):
        return child
    return root


def resolve_recording_root(configured: Path | None) -> Path | None:
    """설정에 지정한 폴더가 있으면 바로잡아서, 없으면 자동 탐지로 녹화 폴더를 정한다."""
    if configured:
        return normalize_recording_root(Path(configured))
    return discover_recording_root()
