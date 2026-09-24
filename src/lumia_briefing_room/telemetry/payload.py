"""클립 메타데이터를 전송 계약(`Label`)으로 바꾼다. 보내지 않는 필드는 여기서 걸러지고, 값은 계약의 형식·길이로 다듬는다.

로컬에는 `pvp`/`pve` 로 저장돼 있고 서버에는 중립 값 `combat`/`other` 로 보낸다. 키는 설치 ID 를 소금으로 한 해시라
경로·시각 원문이 나가지 않고 다른 설치와 이어 볼 수도 없다.
"""

from __future__ import annotations

import hashlib
import json
import math

from lumia_briefing_room.pipeline.label_note import normalize_label_note

WIRE_LABELS = {"pvp": "combat", "pve": "other"}
LABEL_SOURCES = ("user", "migrated")

_STR = "str"
_BOOL = "bool"
_INT = "int"
_FLOAT = "float"

# 필드 → (종류, 최대 길이 또는 (최소, 최대)). 계약의 `sent` 분류와 정확히 같아야 한다(테스트가 대조).
_SPECS: dict[str, tuple[str, object]] = {
    "gameMode": (_STR, 32), "sourceWidth": (_INT, (1, 20000)), "sourceHeight": (_INT, (1, 20000)),
    "sourceIncomplete": (_BOOL, None), "prerollSource": (_STR, 32), "audioStatus": (_STR, 32),
    "durationSec": (_FLOAT, (0, None)), "combatStartOffsetSec": (_FLOAT, (0, None)),
    "combatEndOffsetSec": (_FLOAT, (0, None)), "pvpScore": (_FLOAT, (0, 1)),
    "teamWipe": (_STR, 32), "enemyRingMean": (_FLOAT, (None, None)), "ultimateDelta": (_FLOAT, (None, None)),
    "killDelta": (_INT, (None, None)), "assistDelta": (_INT, (None, None)), "died": (_BOOL, None),
    "detectorConfidence": (_FLOAT, (None, None)), "region": (_STR, 64), "gameDay": (_INT, (None, None)),
    "dayNight": (_STR, 16), "phaseIndex": (_INT, (None, None)), "reviveCost": (_STR, 16),
    "myCharacter": (_STR, 64), "matchKills": (_INT, (0, None)), "matchAssists": (_INT, (0, None)),
    "matchTeamKills": (_INT, (0, None)), "labelConflict": (_BOOL, None),
}
_LISTS = {"tags": (32, 64), "pvpSignals": (64, 64)}
SENT_FIELDS = tuple(_SPECS) + tuple(_LISTS) + ("labelSource",)


def normalize_label_value(value) -> str | None:
    return WIRE_LABELS.get(value) if isinstance(value, str) else None


def hash_key(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:32]


_DISPLAY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def display_id(install_id: str) -> str:
    digest = hashlib.sha256(install_id.encode("utf-8")).digest()
    chars = "".join(_DISPLAY_ALPHABET[b % len(_DISPLAY_ALPHABET)] for b in digest[:8])
    return f"LUMIA-{chars[:4]}-{chars[4:]}"


def _in_range(value: float, bounds) -> bool:
    low, high = bounds
    return (low is None or value >= low) and (high is None or value <= high)


def _clean_scalar(kind: str, limit, value):
    if value is None:
        return None
    if kind == _BOOL:
        return value if isinstance(value, bool) else None
    if kind == _STR:
        return value[:limit] if isinstance(value, str) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if kind == _INT:
        if isinstance(value, float):
            if not value.is_integer():
                return None
            value = int(value)
        return value if _in_range(value, limit) else None
    return value if _in_range(value, limit) else None


def _match_key(meta: dict, clip_id: str, install_id: str) -> str:
    if meta.get("source") == "vod" and meta.get("vodId") is not None:
        return hash_key(install_id, "vod", meta.get("vodId"), meta.get("vodGameIndex"))
    if meta.get("sessionDir") and meta.get("matchStartUtc"):
        return hash_key(install_id, meta["sessionDir"], meta["matchStartUtc"])
    return hash_key(install_id, "clip", clip_id)


def build_label(meta: dict, *, clip_id: str, install_id: str) -> dict | None:
    user_label = normalize_label_value(meta.get("userLabel"))
    if user_label is None:
        return None
    label: dict = {
        "userLabel": user_label,
        "matchKey": _match_key(meta, clip_id, install_id),
        "clipKey": hash_key(install_id, clip_id),
        "source": "vod" if meta.get("source") == "vod" else "recording",
    }
    for name, (kind, limit) in _SPECS.items():
        cleaned = _clean_scalar(kind, limit, meta.get(name))
        if cleaned is not None:
            label[name] = cleaned
    for name, (max_items, max_len) in _LISTS.items():
        items = meta.get(name)
        if isinstance(items, list):
            label[name] = [i[:max_len] for i in items if isinstance(i, str)][:max_items]
    if meta.get("labelSource") in LABEL_SOURCES:
        label["labelSource"] = meta["labelSource"]
    try:
        note = normalize_label_note(meta.get("labelNote"))
    except ValueError:
        note = None
    if note:
        label["labelNote"] = note
    stamp = meta.get("labeledAt")
    if isinstance(stamp, str) and stamp:
        label["labeledAt"] = stamp[:40]
    values = meta.get("pvpSignalValues")
    if isinstance(values, dict):
        numbers = {
            k[:64]: float(v) for k, v in values.items()
            if isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
        }
        if numbers:
            label["pvpSignalValues"] = dict(list(numbers.items())[:64])
    return label


def label_digest(label: dict) -> str:
    return hashlib.sha256(json.dumps(label, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
