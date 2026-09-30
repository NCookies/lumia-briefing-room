from pathlib import Path

from fastapi.testclient import TestClient

from lumia_briefing_room.api import disk_routes
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig
from lumia_briefing_room.pipeline.disk_space import GB, DiskStatus
from lumia_briefing_room.pipeline.notices import notices


def _client(tmp_path: Path):
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp"))
    return TestClient(create_app(cfg, config_path=tmp_path / "config.json"))


def _status(free_gb, low=False):
    return DiskStatus(free_bytes=free_gb * GB, expected_bytes=3 * GB, threshold_bytes=20 * GB, low=low, message=None)


def test_disk_report_shows_free_space_and_flags_below_recommended(tmp_path, monkeypatch):
    monkeypatch.setattr(disk_routes.disk_alert, "disk_status", lambda cfg: _status(30))
    body = _client(tmp_path).get("/api/disk").json()
    assert body["available"] is True and body["freeGb"] == 30.0
    assert body["belowRecommended"] is True and body["low"] is False
    assert body["recommendedGb"] == [50, 100]


def test_disk_report_when_the_drive_cannot_be_read(tmp_path, monkeypatch):
    def boom(cfg):
        raise OSError("no drive")

    monkeypatch.setattr(disk_routes.disk_alert, "disk_status", boom)
    assert _client(tmp_path).get("/api/disk").json()["available"] is False


def test_notices_can_be_listed_and_dismissed(tmp_path):
    notices.clear("t_kind")
    notices.post("t_kind", "hello")
    client = _client(tmp_path)
    assert any(n["kind"] == "t_kind" for n in client.get("/api/notices").json()["notices"])
    assert client.post("/api/notices/t_kind/dismiss").status_code == 200
    assert client.post("/api/notices/t_kind/dismiss").status_code == 404


def test_first_run_includes_the_disk_report(tmp_path, monkeypatch):
    monkeypatch.setattr(disk_routes.disk_alert, "disk_status", lambda cfg: _status(80))
    body = _client(tmp_path).get("/api/first-run").json()
    assert body["disk"]["freeGb"] == 80.0
