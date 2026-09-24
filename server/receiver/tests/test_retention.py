import os
import time
from uuid import uuid4

from app.retention import purge_expired

DAY = 86400


def _touch(path, age_days):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    stamp = time.time() - age_days * DAY
    os.utime(path, (stamp, stamp))
    return path


def test_purges_only_old_logs_and_diagnostics(tmp_path):
    iid = uuid4()
    old_log = _touch(tmp_path / "logs" / str(iid) / "old.jsonl", 91)
    new_log = _touch(tmp_path / "logs" / str(iid) / "new.jsonl", 10)
    old_diag = _touch(tmp_path / "diagnostics" / str(iid) / "R-1.json", 100)
    label = _touch(tmp_path / "labels" / str(iid) / "keep.json", 500)

    removed = purge_expired(tmp_path, days=90)

    assert removed == 2
    assert not old_log.exists() and not old_diag.exists()
    assert new_log.exists() and label.exists()


def test_purges_dev_mode_data_too_and_removes_empty_install_dirs(tmp_path):
    iid = uuid4()
    _touch(tmp_path / "dev" / "logs" / str(iid) / "old.jsonl", 200)
    purge_expired(tmp_path, days=90)
    assert not (tmp_path / "dev" / "logs" / str(iid)).exists()


def test_purge_on_missing_data_dir_is_a_noop(tmp_path):
    assert purge_expired(tmp_path / "nope", days=90) == 0


def test_server_purges_expired_files_at_startup(tmp_path):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    iid = uuid4()
    old = _touch(tmp_path / "logs" / str(iid) / "old.jsonl", 91)
    settings = Settings(data_dir=tmp_path, api_tokens=("t",), max_body_bytes=1000, purge_interval_sec=3600)
    with TestClient(create_app(settings)):
        time.sleep(0.3)
    assert not old.exists()
