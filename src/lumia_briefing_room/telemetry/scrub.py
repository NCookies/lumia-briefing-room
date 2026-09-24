"""서버로 보내는 오류 로그에서 개인정보를 지운다. (roadmap §4-5, plan-deploy.md D10)

지우는 것: 닉네임, Windows 사용자 이름(알려진 것과 모르는 것 모두), 절대 경로 속 폴더 이름(파일 이름만 남김),
UNC·POSIX 홈 경로. 트레이스백의 소스 경로는 패키지 기준 상대 경로로 줄여 개발 PC·설치본이 같은 모양이 되게 한다.
"""

from __future__ import annotations

import hashlib
import re

from lumia_briefing_room.diagnostics import scrub_text

MESSAGE_MAX = 2000
STACK_MAX = 8000
_PACKAGE = "lumia_briefing_room"

_USER_DIR = re.compile(r"(?P<pre>[\\/]Users[\\/])(?P<name>[^\\/\s\"']+)", re.IGNORECASE)
_DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\"'<>|*?\r\n]*")
_UNC_PATH = re.compile(r"\\\\[^\s\"'<>|*?]+")
_POSIX_HOME = re.compile(r"(?<![\w.])/(?:home|Users|root)(?:/[^\s\"']*)?")
_FILE_LINE = re.compile(r'(File ")([^"]+)(", line \d+, in )(\S+)')
_LAST_FRAME = re.compile(r'File "([^"]+)", line \d+, in (\S+)')
_DIGITS = re.compile(r"\d+")
_SPLIT = re.compile(r"[\\/]")


def _parts(path: str) -> list[str]:
    return [p for p in _SPLIT.split(path) if p]


def _relative_source(path: str) -> str:
    """소스 경로를 패키지 기준 상대 경로로. 패키지가 아니면 site-packages·_internal 이하, 그도 아니면 파일 이름만 남긴다."""
    parts = _parts(path)
    lowered = [p.lower() for p in parts]
    for marker in (_PACKAGE, "site-packages", "_internal"):
        if marker in lowered:
            index = len(lowered) - 1 - lowered[::-1].index(marker)
            start = index if marker == _PACKAGE else index + 1
            if start < len(parts):
                return "\\".join(parts[start:])
    return parts[-1] if parts else path


def _basename_path(match: re.Match) -> str:
    parts = _parts(match.group(0))
    return "<path>\\" + parts[-1] if parts else "<path>"


def _posix_path(match: re.Match) -> str:
    parts = [p for p in match.group(0).split("/") if p]
    return "<path>/" + parts[-1] if len(parts) > 2 else "<path>"


def _scrub_paths(text: str) -> str:
    text = _UNC_PATH.sub(_basename_path, text)
    text = _DRIVE_PATH.sub(_basename_path, text)
    text = _POSIX_HOME.sub(_posix_path, text)
    return _USER_DIR.sub(lambda m: m.group("pre") + "<user>", text)


def scrub_message(text, *, usernames, nicknames) -> str:
    if text is None:
        return ""
    text = scrub_text(_scrub_paths(str(text)), usernames=usernames, nicknames=nicknames)
    return text[:MESSAGE_MAX]


def scrub_stack(text, *, usernames, nicknames) -> str:
    text = _FILE_LINE.sub(lambda m: f"{m.group(1)}{_relative_source(m.group(2))}{m.group(3)}{m.group(4)}", str(text))
    text = scrub_text(_scrub_paths(text), usernames=usernames, nicknames=nicknames)
    return text[-STACK_MAX:]


def make_fingerprint(logger, exception_type, stack, message) -> str:
    """같은 오류를 묶어 세기 위한 지문. 예외가 있으면 (로거, 예외 종류, 마지막 프레임의 파일·함수), 없으면 숫자를 지운 메시지.
    줄 번호는 버전마다 바뀌므로 넣지 않는다."""
    frames = _LAST_FRAME.findall(stack) if stack else []
    if exception_type and frames:
        path, func = frames[-1]
        basis = f"{logger}|{exception_type}|{_relative_source(path)}|{func}"
    else:
        basis = f"{logger}|{_DIGITS.sub('#', str(message or ''))}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def scrub_entry(entry: dict, *, usernames, nicknames) -> dict:
    """outbox 항목 하나를 계약의 `LogEntry` 로. 개인정보를 지우고 길이를 맞추고 오류 지문을 붙인다."""
    message = scrub_message(entry.get("message"), usernames=usernames, nicknames=nicknames)
    out = {
        "ts": str(entry.get("ts", ""))[:40],
        "level": str(entry.get("level", "ERROR"))[:16],
        "message": message,
    }
    logger = entry.get("logger")
    if isinstance(logger, str) and logger:
        out["logger"] = logger[:128]
    exception_type = entry.get("exceptionType")
    stack = entry.get("stack")
    if isinstance(exception_type, str) and exception_type:
        out["exceptionType"] = exception_type[:128]
    if isinstance(stack, str) and stack:
        out["stack"] = scrub_stack(stack, usernames=usernames, nicknames=nicknames)
    out["fingerprint"] = make_fingerprint(out.get("logger"), out.get("exceptionType"), out.get("stack"), message)
    return out
