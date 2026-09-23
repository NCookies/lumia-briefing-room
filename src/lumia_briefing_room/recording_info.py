"""스팀 녹화 폴더에서 가장 최근 녹화 세션의 해상도·코덱을 읽는다. (plan-deploy.md D3)"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from lumia_briefing_room.video.session import RecordingSession, SessionParseError

ETERNAL_RETURN_APP_ID = 1049590
_FOLDER = re.compile(r"^bg_(\d+)_(\d{8})_(\d{6})$")


@dataclass(frozen=True)
class SessionInfo:
    name: str
    width: int
    height: int
    codec: str | None


def _video_codec(mpd_path: Path) -> str | None:
    try:
        root = ET.fromstring(mpd_path.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError):
        return None
    representation = root.find(".//{*}AdaptationSet[@contentType='video']/{*}Representation")
    return representation.get("codecs") if representation is not None else None


def _candidates(recording_root: Path) -> list[tuple[bool, str, Path]]:
    found = []
    try:
        entries = list(recording_root.iterdir())
    except OSError:
        return []
    for entry in entries:
        match = _FOLDER.match(entry.name)
        if match and entry.is_dir():
            is_er = int(match.group(1)) == ETERNAL_RETURN_APP_ID
            found.append((is_er, match.group(2) + match.group(3), entry))
    return sorted(found, key=lambda item: (item[0], item[1]), reverse=True)


def find_latest_session(recording_root: Path | None) -> SessionInfo | None:
    """이터널 리턴 세션을 우선하고, 그중 가장 최근이면서 session.mpd 를 읽을 수 있는 것을 고른다."""
    if recording_root is None:
        return None
    for _, _, folder in _candidates(recording_root):
        try:
            session = RecordingSession.load(folder)
        except (SessionParseError, OSError, ValueError, TypeError):
            continue
        return SessionInfo(folder.name, session.width, session.height, _video_codec(folder / "session.mpd"))
    return None
