"""관리자 전용 읽기 조회: 진단 번들·오류 로그·서버 상태. (앱 저장소 관리자 화면이 쓴다)

저장된 파일을 읽어 보여 주기만 한다. IP 는 다루지 않는다(차단된 수만 센다).
"""

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

RECEIPT_PATTERN = re.compile(r"^R-\d{8}-[A-Z0-9]{6}$")
MAX_GROUPS = 200
GROUP_MESSAGE_LEN = 300


def _base(root: Path, mode: str) -> Path:
    return root / "dev" if mode == "dev" else root


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _iso_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _install_dirs(base: Path, kind: str):
    kind_dir = base / kind
    if not kind_dir.is_dir():
        return
    for install_dir in sorted(kind_dir.iterdir()):
        if install_dir.is_dir():
            yield install_dir


def list_diagnostics(root: Path, mode: str, q: str, limit: int, offset: int) -> tuple[list[dict], int]:
    needle = q.strip().lower()
    items = []
    for install_dir in _install_dirs(_base(root, mode), "diagnostics"):
        for path in install_dir.glob("*.json"):
            record = _read_json(path)
            if record is None:
                continue
            entries = record.get("entries") or []
            env = record.get("env") or {}
            item = {
                "receiptId": record.get("receiptId", path.stem),
                "displayId": record.get("displayId"),
                "installId": install_dir.name,
                "receivedAt": record.get("receivedAt", ""),
                "appVersion": env.get("appVersion"),
                "os": env.get("os"),
                "entryCount": len(entries),
                "errorCount": sum(1 for e in entries if e.get("level") in ("ERROR", "CRITICAL")),
            }
            if needle and not (
                needle in item["receiptId"].lower()
                or needle in (item["displayId"] or "").lower()
                or item["installId"].lower().startswith(needle)
            ):
                continue
            items.append(item)
    items.sort(key=lambda i: (i["receivedAt"], i["receiptId"]), reverse=True)
    return items[offset : offset + limit], len(items)


def get_diagnostic(root: Path, mode: str, receipt_id: str) -> dict | None:
    if not RECEIPT_PATTERN.match(receipt_id):
        return None
    for install_dir in _install_dirs(_base(root, mode), "diagnostics"):
        path = install_dir / f"{receipt_id}.json"
        if path.is_file():
            record = _read_json(path)
            if record is not None:
                return {"installId": install_dir.name, **record}
    return None


def _log_entries(root: Path, mode: str, install_id: str = ""):
    for install_dir in _install_dirs(_base(root, mode), "logs"):
        if install_id and install_dir.name != install_id:
            continue
        for path in sorted(install_dir.glob("*.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                try:
                    batch = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(batch, dict):
                    continue
                version = (batch.get("env") or {}).get("appVersion")
                for entry in batch.get("entries") or []:
                    yield {
                        "installId": install_dir.name,
                        "receivedAt": batch.get("receivedAt", ""),
                        "appVersion": version,
                        **entry,
                    }


def list_log_entries(
    root: Path, mode: str, *, install_id: str, level: str, q: str, limit: int, offset: int
) -> tuple[list[dict], int]:
    needle = q.strip().lower()
    found = []
    for entry in _log_entries(root, mode, install_id):
        if level and entry.get("level") != level:
            continue
        if needle and needle not in (entry.get("message", "") + " " + (entry.get("exceptionType") or "")).lower():
            continue
        found.append(entry)
    found.sort(key=lambda e: (e.get("ts", ""), e["receivedAt"]), reverse=True)
    return found[offset : offset + limit], len(found)


def group_log_entries(root: Path, mode: str) -> list[dict]:
    groups: dict[tuple, dict] = {}
    for entry in _log_entries(root, mode):
        fingerprint = entry.get("fingerprint")
        message = entry.get("message", "")[:GROUP_MESSAGE_LEN]
        key = (fingerprint,) if fingerprint else (None, entry.get("exceptionType"), message)
        ts = entry.get("ts", "")
        group = groups.get(key)
        if group is None:
            group = groups[key] = {
                "fingerprint": fingerprint,
                "count": 0,
                "installIds": set(),
                "level": entry.get("level"),
                "exceptionType": entry.get("exceptionType"),
                "message": message,
                "firstSeen": ts,
                "lastSeen": ts,
            }
        group["count"] += 1
        group["installIds"].add(entry["installId"])
        group["firstSeen"] = min(group["firstSeen"], ts)
        if ts >= group["lastSeen"]:
            group["lastSeen"] = ts
            group["message"] = message
            group["level"] = entry.get("level")
    result = []
    for group in groups.values():
        group["installs"] = len(group.pop("installIds"))
        result.append(group)
    result.sort(key=lambda g: (g["count"], g["lastSeen"]), reverse=True)
    return result[:MAX_GROUPS]


def _dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else 0


def _mode_status(base: Path) -> dict:
    label_files = [p for d in _install_dirs(base, "labels") for p in d.glob("*.json")]
    log_files = [p for d in _install_dirs(base, "logs") for p in d.glob("*.jsonl")]
    diag_files = [p for d in _install_dirs(base, "diagnostics") for p in d.glob("*.json")]
    installs = {d.name for kind in ("labels", "logs", "diagnostics") for d in _install_dirs(base, kind)}

    def last(paths: list[Path]) -> str | None:
        return max((_iso_mtime(p) for p in paths), default=None)

    return {
        "labels": len(label_files),
        "logEntryFiles": len(log_files),
        "diagnostics": len(diag_files),
        "installs": len(installs),
        "lastReceived": {"labels": last(label_files), "logs": last(log_files), "diagnostics": last(diag_files)},
    }


def server_status(root: Path, *, blocked_ips: int, retention_days: int) -> dict:
    now = datetime.now(timezone.utc)
    stats = _read_json(root / "stats" / f"{now:%Y-%m-%d}.json") or {}
    usage = shutil.disk_usage(root if root.exists() else root.parent)
    return {
        "release": _mode_status(_base(root, "release")),
        "dev": _mode_status(_base(root, "dev")),
        "today": {"requests": stats.get("requests", {}), "rejected": stats.get("rejected", {})},
        "disk": {
            "totalBytes": usage.total,
            "usedPercent": round(usage.used / usage.total * 100, 1) if usage.total else 0,
            "dataBytes": _dir_size(root),
        },
        "blockedIps": blocked_ips,
        "retentionDays": retention_days,
        "serverTime": now.isoformat(),
    }
