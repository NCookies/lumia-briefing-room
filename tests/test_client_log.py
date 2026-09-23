import logging

from fastapi.testclient import TestClient

from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config
from lumia_briefing_room.logsetup import default_log_path, setup_file_logging


def _client():
    return TestClient(create_app(Config()))


def test_client_log_writes_client_prefixed_line(caplog):
    payload = {"level": "error", "message": "boom", "stack": "at x", "url": "http://127.0.0.1:8765/", "time": "t"}
    with caplog.at_level(logging.INFO):
        resp = _client().post("/api/client-log", json=payload)
    assert resp.status_code == 204
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "[client]" in text and "boom" in text and "at x" in text


def test_client_log_rejects_missing_message():
    assert _client().post("/api/client-log", json={"level": "error"}).status_code == 422


def test_client_log_truncates_huge_message(caplog):
    with caplog.at_level(logging.INFO):
        _client().post("/api/client-log", json={"message": "x" * 100000})
    assert max(len(r.getMessage()) for r in caplog.records) < 10000


def test_setup_file_logging_writes_server_and_client_lines(tmp_path):
    path = tmp_path / "logs" / "app.log"
    handler = setup_file_logging(path)
    try:
        logging.getLogger("lumia_briefing_room.client").warning("[client] hello")
    finally:
        logging.getLogger("lumia_briefing_room").removeHandler(handler)
        handler.close()
    assert "[client] hello" in path.read_text(encoding="utf-8")


def test_default_log_path_is_under_local_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_log_path() == tmp_path / "LumiaBriefingRoom" / "logs" / "app.log"
