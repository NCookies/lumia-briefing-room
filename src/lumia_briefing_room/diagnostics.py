"""진단 정보 zip. 사용자가 직접 첨부해 보내는 용도라 닉네임·사용자 이름을 지운다. (plan-deploy.md D3)"""

import io
import json
import re
import zipfile
from pathlib import Path

MIN_STANDALONE_NAME_LEN = 3
_USER_PATH = r"(?P<prefix>[\\/]Users[\\/])(?P<name>{name})(?=[\\/\s\"']|$)"
_DROPPED_CONFIG_KEYS = {("telemetry", "installId")}


def _clean(names) -> list[str]:
    return [n.strip() for n in names if n and n.strip()]


def scrub_text(text: str, *, usernames, nicknames) -> str:
    for name in _clean(usernames):
        text = re.sub(_USER_PATH.format(name=re.escape(name)), r"\g<prefix><user>", text, flags=re.IGNORECASE)
        if len(name) >= MIN_STANDALONE_NAME_LEN:
            text = re.sub(re.escape(name), "<user>", text, flags=re.IGNORECASE)
    for name in _clean(nicknames):
        text = re.sub(re.escape(name), "<nickname>", text, flags=re.IGNORECASE)
    return text


def _scrub_value(value, *, usernames, nicknames):
    if isinstance(value, str):
        return scrub_text(value, usernames=usernames, nicknames=nicknames)
    if isinstance(value, list):
        return [_scrub_value(v, usernames=usernames, nicknames=nicknames) for v in value]
    if isinstance(value, dict):
        return {k: _scrub_value(v, usernames=usernames, nicknames=nicknames) for k, v in value.items()}
    return value


def scrub_config(config: dict, *, usernames, nicknames) -> dict:
    scrubbed = _scrub_value(config, usernames=usernames, nicknames=nicknames)
    for section, key in _DROPPED_CONFIG_KEYS:
        if isinstance(scrubbed.get(section), dict):
            scrubbed[section].pop(key, None)
    return scrubbed


def _log_files(log_dir: Path) -> list[Path]:
    if not log_dir.is_dir():
        return []
    return sorted(p for p in log_dir.iterdir() if p.is_file() and ".log" in p.name)


def _dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def build_diagnostics_zip(*, log_dir: Path, info: dict, config: dict, usernames, nicknames) -> bytes:
    def scrub(text: str) -> str:
        return scrub_text(text, usernames=usernames, nicknames=nicknames)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("info.json", scrub(_dump(_scrub_value(info, usernames=usernames, nicknames=nicknames))))
        zf.writestr("config.json", _dump(scrub_config(config, usernames=usernames, nicknames=nicknames)))
        for path in _log_files(log_dir):
            zf.writestr(f"logs/{path.name}", scrub(path.read_text(encoding="utf-8", errors="replace")))
    return buffer.getvalue()
