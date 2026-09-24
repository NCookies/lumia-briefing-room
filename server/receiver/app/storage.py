import json
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

KINDS = ("labels", "logs", "diagnostics")
_RECEIPT_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def mode_roots(root: Path) -> list[Path]:
    """운영 데이터(root)와 개발 모드 데이터(root/dev)는 폴더가 분리돼 있다."""
    return [root, root / "dev"]


class FileStore:
    def __init__(self, root: Path):
        self.root = root

    def _dir(self, mode: str, kind: str, install_id: UUID) -> Path:
        base = self.root / "dev" if mode == "dev" else self.root
        path = base / kind / str(install_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _write(path: Path, record: dict) -> None:
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    def save_labels(self, mode: str, install_id: UUID, app_version: str, schema_version: int, labels: list[dict]) -> int:
        target = self._dir(mode, "labels", install_id)
        received = datetime.now(timezone.utc).isoformat()
        for label in labels:
            record = {"receivedAt": received, "appVersion": app_version, "schemaVersion": schema_version, "label": label}
            self._write(target / f"{label['clipKey']}.json", record)
        return len(labels)

    def append_log(self, mode: str, install_id: UUID, record: dict) -> None:
        now = datetime.now(timezone.utc)
        line = {"receivedAt": now.isoformat(), **record}
        path = self._dir(mode, "logs", install_id) / f"{now:%Y-%m-%d}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def save_diagnostic(self, mode: str, install_id: UUID, record: dict) -> str:
        now = datetime.now(timezone.utc)
        suffix = "".join(secrets.choice(_RECEIPT_ALPHABET) for _ in range(6))
        receipt = f"R-{now:%Y%m%d}-{suffix}"
        self._write(self._dir(mode, "diagnostics", install_id) / f"{receipt}.json",
                    {"receivedAt": now.isoformat(), "receiptId": receipt, **record})
        return receipt

    def delete_install(self, install_id: UUID) -> bool:
        removed = False
        for base in mode_roots(self.root):
            for kind in KINDS:
                path = base / kind / str(install_id)
                if path.exists():
                    shutil.rmtree(path)
                    removed = True
        return removed
