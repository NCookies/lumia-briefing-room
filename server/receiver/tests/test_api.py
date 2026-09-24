import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

TOKEN = "secret"


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path, api_token=TOKEN, max_body_bytes=10_000)
    return TestClient(create_app(settings)), tmp_path


def headers(token=TOKEN):
    return {"X-Api-Token": token}


def label_body(install_id, **label):
    return {"installId": str(install_id), "appVersion": "0.1.0", "labels": [label]}


def test_healthz_needs_no_token(client):
    c, _ = client
    assert c.get("/healthz").json() == {"status": "ok"}


def test_rejects_missing_or_wrong_token(client):
    c, _ = client
    body = label_body(uuid4(), userLabel="pvp")
    assert c.post("/v1/labels", json=body).status_code == 401
    assert c.post("/v1/labels", json=body, headers=headers("nope")).status_code == 401


def test_saves_label_and_drops_unknown_fields(client):
    c, root = client
    iid = uuid4()
    body = label_body(
        iid, userLabel="pvp", pvpScore=1.0, pvpSignals=["kill_delta"],
        nickname="secret-nick", videoPath="C:/Users/me/clip.mp4",
    )
    r = c.post("/v1/labels", json=body, headers=headers())
    assert r.status_code == 200 and r.json() == {"saved": 1}
    files = list((root / "labels" / str(iid)).glob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))["label"]
    assert saved == {"userLabel": "pvp", "pvpScore": 1.0, "pvpSignals": ["kill_delta"], "tags": []}
    assert "nickname" not in saved and "videoPath" not in saved


def test_rejects_invalid_install_id_and_score(client):
    c, _ = client
    bad_id = {"installId": "../../etc", "appVersion": "1", "labels": []}
    assert c.post("/v1/labels", json=bad_id, headers=headers()).status_code == 422
    bad_score = label_body(uuid4(), pvpScore=7)
    assert c.post("/v1/labels", json=bad_score, headers=headers()).status_code == 422


def test_appends_logs_per_day(client):
    c, root = client
    iid = uuid4()
    body = {
        "installId": str(iid),
        "env": {"appVersion": "0.1.0", "os": "Windows 11", "resolution": "1920x1080"},
        "entries": [{"ts": "2026-09-24T10:00:00", "level": "ERROR", "message": "boom"}],
    }
    assert c.post("/v1/logs", json=body, headers=headers()).json() == {"saved": 1}
    assert c.post("/v1/logs", json=body, headers=headers()).status_code == 200
    (log,) = (root / "logs" / str(iid)).glob("*.jsonl")
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["entries"][0]["message"] == "boom"


def test_rejects_oversized_body(client):
    c, _ = client
    body = label_body(uuid4(), region="x" * 20_000)
    assert c.post("/v1/labels", json=body, headers=headers()).status_code == 413


def test_delete_install_removes_everything(client):
    c, root = client
    iid = uuid4()
    c.post("/v1/labels", json=label_body(iid, userLabel="hunt"), headers=headers())
    assert c.delete(f"/v1/installs/{iid}", headers=headers()).json() == {"deleted": True}
    assert not (root / "labels" / str(iid)).exists()
    assert c.delete(f"/v1/installs/{iid}", headers=headers()).json() == {"deleted": False}
