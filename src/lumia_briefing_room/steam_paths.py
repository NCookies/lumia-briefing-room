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


def discover_recording_root(steam_path: Path | None = None) -> Path | None:
    """스팀의 배경 녹화 저장 위치(`<BackgroundRecordPath>\\video`)를 자동으로 찾는다.

    스팀 설치를 못 찾거나, 어느 계정에도 배경 녹화 경로가 설정되어 있지 않으면
    None 을 돌려준다 — 호출자가 --recording-root 를 요구하는 등으로 대체해야 한다.
    """
    steam_path = steam_path if steam_path is not None else find_steam_install_path()
    if steam_path is None:
        return None
    record_path = read_background_record_path(steam_path)
    if record_path is None:
        return None
    return record_path / "video"
