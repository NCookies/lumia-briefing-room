import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4


class FileStore:
    def __init__(self, root: Path):
        self.root = root

    def _dir(self, kind: str, install_id: UUID) -> Path:
        path = self.root / kind / str(install_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_labels(self, install_id: UUID, app_version: str, labels: list[dict]) -> int:
        target = self._dir("labels", install_id)
        received = datetime.now(timezone.utc).isoformat()
        for label in labels:
            record = {"receivedAt": received, "appVersion": app_version, "label": label}
            (target / f"{uuid4().hex}.json").write_text(
                json.dumps(record, ensure_ascii=False), encoding="utf-8"
            )
        return len(labels)

    def append_log(self, install_id: UUID, record: dict) -> None:
        now = datetime.now(timezone.utc)
        line = {"receivedAt": now.isoformat(), **record}
        path = self._dir("logs", install_id) / f"{now:%Y-%m-%d}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def delete_install(self, install_id: UUID) -> bool:
        removed = False
        for kind in ("labels", "logs"):
            path = self.root / kind / str(install_id)
            if path.exists():
                shutil.rmtree(path)
                removed = True
        return removed
