"""오류 로그·진단 번들 자동 삭제(docs/privacy.md 의 보관 기간). 라벨은 삭제 요청 전까지 보관하므로 건드리지 않는다."""

import time
from pathlib import Path

from .storage import mode_roots

EXPIRING_KINDS = ("logs", "diagnostics")


def purge_expired(root: Path, days: int, now: float | None = None) -> int:
    cutoff = (time.time() if now is None else now) - days * 86400
    removed = 0
    for base in mode_roots(root):
        for kind in EXPIRING_KINDS:
            kind_dir = base / kind
            if not kind_dir.is_dir():
                continue
            for install_dir in kind_dir.iterdir():
                if not install_dir.is_dir():
                    continue
                for path in install_dir.iterdir():
                    if path.is_file() and path.stat().st_mtime < cutoff:
                        path.unlink()
                        removed += 1
                if not any(install_dir.iterdir()):
                    install_dir.rmdir()
    return removed
