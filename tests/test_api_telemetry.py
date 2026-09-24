import json

import httpx
import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, dataclass_from_camel_dict, load_config, save_config
from lumia_briefing_room.telemetry.client import ReceiverClient
from lumia_briefing_room.telemetry.outbox import Outbox
from lumia_briefing_room.telemetry.sender import TelemetrySender


class Fake:
    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.config_path = tmp_path / "config.json"
        (tmp_path / "clips").mkdir()
        (tmp_path / "vod").mkdir()
        self.outbox = Outbox(tmp_path / "outbox.jsonl")
        self.status = 200
        self.calls = []
        cfg = dataclass_from_camel_dict(Config, {
            "paths": {"clips": str(tmp_path / "clips"), "vodClips": str(tmp_path / "vod")},
            "telemetry": {"sendLabels": True, "sendLogs": True, "apiToken": "tok", "serverUrl": "https://r.example"},
        })
        save_config(cfg, self.config_path)
        self.cfg = cfg

    def handler(self, request):
        self.calls.append(request)
        if self.status == "boom":
            raise httpx.ConnectError("refused")
        return httpx.Response(self.status, json={"deleted": True})

    def sender(self):
        return TelemetrySender(
            config_path=self.config_path, state_path=self.tmp / "state.json", outbox=self.outbox,
            client_factory=lambda e: ReceiverClient(e, transport=httpx.MockTransport(self.handler)),
            frozen=True, collect_env=lambda cfg: {"appVersion": "0.1.1", "os": "Windows 11"}, usernames=["tester"],
        )


@pytest.fixture
def fake(tmp_path):
    return Fake(tmp_path)


@pytest.fixture
def client(fake):
    app = create_app(fake.cfg, config_path=fake.config_path)
    app.state.telemetry_sender = fake.sender()
    return TestClient(app)


def add_label(fake, clip_id="c1", **over):
    meta = {"userLabel": "pvp", "labelNote": "메모", "title": "제목", "sessionDir": "s", "matchStartUtc": "t"}
    meta.update(over)
    (fake.tmp / "clips" / f"{clip_id}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def test_status_reports_ids_consent_and_pending_counts(client, fake):
    add_label(fake)
    fake.outbox.append({"ts": "t", "level": "ERROR", "message": "m"})
    body = client.get("/api/telemetry/status").json()
    assert body["sendLabels"] is True and body["pendingLabels"] == 1 and body["pendingLogs"] == 1
    assert body["displayId"].startswith("LUMIA-") and len(body["installId"]) == 36
    assert body["canSendInThisMode"] is True and body["endpointConfigured"] is True


def test_preview_returns_what_would_be_sent_including_the_label_note_and_scrubbed_logs(client, fake):
    add_label(fake)
    fake.outbox.append({"ts": "t", "level": "ERROR", "message": r"C:\Users\tester\a.mp4 열 수 없다"})
    body = client.get("/api/telemetry/preview").json()
    assert body["labels"]["count"] == 1 and body["labels"]["items"][0]["labelNote"] == "메모"
    assert "제목" not in json.dumps(body, ensure_ascii=False)
    assert "tester" not in json.dumps(body, ensure_ascii=False) and body["logs"]["count"] == 1
    assert fake.calls == []


def test_delete_succeeds_turns_sending_off_and_reports_it(client, fake):
    result = client.post("/api/telemetry/delete")
    assert result.status_code == 200 and result.json()["ok"] is True
    cfg = load_config(fake.config_path)
    assert cfg.telemetry.send_labels is False and cfg.telemetry.send_logs is False
    assert fake.calls[0].method == "DELETE"


def test_delete_reports_a_readable_error_when_the_server_is_unreachable(client, fake):
    fake.status = "boom"
    result = client.post("/api/telemetry/delete")
    assert result.status_code == 502 and "연결" in result.json()["detail"]
    assert load_config(fake.config_path).telemetry.send_labels is True


def test_delete_reports_a_readable_error_on_a_server_error(client, fake):
    fake.status = 500
    result = client.post("/api/telemetry/delete")
    assert result.status_code == 502 and "500" in result.json()["detail"]


def test_delete_without_a_token_says_the_build_has_no_server_info(fake, monkeypatch):
    monkeypatch.delenv("LUMIA_RECEIVER_TOKEN", raising=False)
    monkeypatch.setattr("lumia_briefing_room.telemetry.endpoint.bundled_endpoint", lambda: {})
    cfg = load_config(fake.config_path)
    cfg.telemetry.api_token = ""
    save_config(cfg, fake.config_path)
    app = create_app(cfg, config_path=fake.config_path)
    app.state.telemetry_sender = fake.sender()
    result = TestClient(app).post("/api/telemetry/delete")
    assert result.status_code == 503 and "서버" in result.json()["detail"]


def test_privacy_text_is_served_for_the_in_app_viewer(client):
    body = client.get("/api/privacy").json()
    assert "개인정보" in body["markdown"] and "lumia.briefingroom@gmail.com" in body["markdown"]


def test_privacy_text_missing_is_a_404(client, monkeypatch, tmp_path):
    monkeypatch.setattr("lumia_briefing_room.api.telemetry_routes.privacy_path", lambda: tmp_path / "none.md")
    assert client.get("/api/privacy").status_code == 404
