import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.test_api import TOKEN, diag_body, headers, label, label_body, log_body


def _client(tmp_path):
    return TestClient(create_app(Settings(data_dir=tmp_path, api_tokens=(TOKEN,), max_body_bytes=100_000)))


def _today(tmp_path):
    path = tmp_path / "stats" / f"{datetime.now(timezone.utc):%Y-%m-%d}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_counts_requests_bytes_and_dropped_field_names(tmp_path):
    c = _client(tmp_path)
    body = label_body(uuid4(), label(nickname="secret-nick", labelNote="비밀 메모"))
    c.post("/v1/labels", json=body, headers=headers())
    c.post("/v1/logs", json=log_body(uuid4()), headers=headers())
    c.post("/v1/diagnostics", json=diag_body(uuid4()), headers=headers())

    stats = _today(tmp_path)
    assert stats["requests"] == {"labels": 1, "logs": 1, "diagnostics": 1}
    assert stats["avgBytes"]["labels"] > 0 and stats["bytes"]["labels"] == stats["avgBytes"]["labels"]
    assert stats["droppedFields"] == {"nickname": 1}


def test_counts_rejected_requests_by_field_name_without_values(tmp_path):
    c = _client(tmp_path)
    c.post("/v1/labels", json=label_body(uuid4(), label(userLabel="pve", labelNote="n" * 501)), headers=headers())

    stats = _today(tmp_path)
    assert stats["rejected"] == {"labels": 1}
    assert stats["rejectedFields"]["userLabel"] == 1 and stats["rejectedFields"]["labelNote"] == 1
    assert "secret" not in json.dumps(stats) and "nnnn" not in json.dumps(stats)


def test_stats_never_contain_label_note_text(tmp_path):
    c = _client(tmp_path)
    c.post("/v1/labels", json=label_body(uuid4(), label(labelNote="내 메모 원문")), headers=headers())
    assert "내 메모 원문" not in json.dumps(_today(tmp_path), ensure_ascii=False)


def test_unauthorized_requests_are_not_counted(tmp_path):
    c = _client(tmp_path)
    c.post("/v1/labels", json=label_body(uuid4()), headers=headers("nope"))
    assert not (tmp_path / "stats").exists()
