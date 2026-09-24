import json
import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

TOKEN = "secret"
KEY_A, KEY_B = "a" * 32, "b" * 32


def make_client(tmp_path, **overrides):
    settings = Settings(data_dir=tmp_path, api_tokens=(TOKEN,), max_body_bytes=10_000, **overrides)
    return TestClient(create_app(settings))


@pytest.fixture
def client(tmp_path):
    return make_client(tmp_path), tmp_path


def headers(token=TOKEN):
    return {"X-Api-Token": token}


def label(clip_key=KEY_B, **extra):
    return {"userLabel": "combat", "matchKey": KEY_A, "clipKey": clip_key, **extra}


def label_body(install_id, *labels, mode="release"):
    return {
        "installId": str(install_id), "appVersion": "0.1.0", "schemaVersion": 1, "mode": mode,
        "labels": list(labels) or [label()],
    }


def log_body(install_id, mode="release"):
    return {
        "installId": str(install_id), "schemaVersion": 1, "mode": mode,
        "env": {"appVersion": "0.1.0", "os": "Windows 11", "resolution": "1920x1080"},
        "entries": [{"ts": "2026-09-24T10:00:00", "level": "ERROR", "message": "boom"}],
    }


def diag_body(install_id, mode="release"):
    return {**log_body(install_id, mode), "displayId": "LUMIA-7K3F-9QX2"}


def test_healthz_needs_no_token(client):
    c, _ = client
    assert c.get("/healthz").json() == {"status": "ok"}


def test_rejects_missing_or_wrong_token(client):
    c, _ = client
    body = label_body(uuid4())
    assert c.post("/v1/labels", json=body).status_code == 401
    assert c.post("/v1/labels", json=body, headers=headers("nope")).status_code == 401


def test_accepts_any_of_several_tokens_so_a_token_can_be_rotated(tmp_path):
    settings = Settings(data_dir=tmp_path, api_tokens=("old", "new"), max_body_bytes=10_000)
    c = TestClient(create_app(settings))
    body = label_body(uuid4())
    assert c.post("/v1/labels", json=body, headers=headers("old")).status_code == 200
    assert c.post("/v1/labels", json=body, headers=headers("new")).status_code == 200
    assert c.post("/v1/labels", json=body, headers=headers("revoked")).status_code == 401


def test_no_configured_token_rejects_everything(tmp_path):
    settings = Settings(data_dir=tmp_path, api_tokens=(), max_body_bytes=10_000)
    c = TestClient(create_app(settings))
    assert c.post("/v1/labels", json=label_body(uuid4()), headers=headers("")).status_code == 401


def test_saves_label_and_drops_unknown_fields(client):
    c, root = client
    iid = uuid4()
    body = label_body(iid, label(pvpScore=1.0, pvpSignals=["kill_delta"], nickname="secret-nick", videoPath="C:/x.mp4"))
    r = c.post("/v1/labels", json=body, headers=headers())
    assert r.status_code == 200 and r.json() == {"saved": 1}
    (path,) = (root / "labels" / str(iid)).glob("*.json")
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["schemaVersion"] == 1 and record["appVersion"] == "0.1.0"
    assert record["label"] == {
        "userLabel": "combat", "matchKey": KEY_A, "clipKey": KEY_B,
        "pvpScore": 1.0, "pvpSignals": ["kill_delta"], "tags": [],
    }


def test_resending_a_label_overwrites_by_clip_key(client):
    c, root = client
    iid = uuid4()
    c.post("/v1/labels", json=label_body(iid, label(labelNote="처음")), headers=headers())
    c.post("/v1/labels", json=label_body(iid, label(userLabel="other", labelNote="고침")), headers=headers())
    (path,) = (root / "labels" / str(iid)).glob("*.json")
    saved = json.loads(path.read_text(encoding="utf-8"))["label"]
    assert saved["userLabel"] == "other" and saved["labelNote"] == "고침"


def test_dev_mode_data_is_kept_apart_from_release_data(client):
    c, root = client
    iid = uuid4()
    c.post("/v1/labels", json=label_body(iid, mode="dev"), headers=headers())
    assert list((root / "dev" / "labels" / str(iid)).glob("*.json"))
    assert not (root / "labels").exists()


def test_rejects_invalid_install_id_and_legacy_label(client):
    c, _ = client
    bad_id = {**label_body(uuid4()), "installId": "../../etc"}
    assert c.post("/v1/labels", json=bad_id, headers=headers()).status_code == 422
    legacy = label_body(uuid4(), label(userLabel="pve"))
    assert c.post("/v1/labels", json=legacy, headers=headers()).status_code == 422


def test_validation_error_response_does_not_echo_the_payload(client):
    c, _ = client
    r = c.post("/v1/labels", json=label_body(uuid4(), label(labelNote="x" * 501)), headers=headers())
    assert r.status_code == 422 and "xxxx" not in r.text


def test_appends_logs_per_day(client):
    c, root = client
    iid = uuid4()
    assert c.post("/v1/logs", json=log_body(iid), headers=headers()).json() == {"saved": 1}
    assert c.post("/v1/logs", json=log_body(iid), headers=headers()).status_code == 200
    (log,) = (root / "logs" / str(iid)).glob("*.jsonl")
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["entries"][0]["message"] == "boom"


def test_diagnostics_returns_receipt_id_and_stores_bundle(client):
    c, root = client
    iid = uuid4()
    r = c.post("/v1/diagnostics", json=diag_body(iid), headers=headers())
    assert r.status_code == 200
    receipt = r.json()["receiptId"]
    assert re.fullmatch(r"R-\d{8}-[A-Z2-9]{6}", receipt) and r.json()["saved"] == 1
    stored = json.loads((root / "diagnostics" / str(iid) / f"{receipt}.json").read_text(encoding="utf-8"))
    assert stored["displayId"] == "LUMIA-7K3F-9QX2" and stored["entries"][0]["message"] == "boom"


def test_each_diagnostic_upload_gets_its_own_receipt(client):
    c, _ = client
    iid = uuid4()
    ids = {c.post("/v1/diagnostics", json=diag_body(iid), headers=headers()).json()["receiptId"] for _ in range(3)}
    assert len(ids) == 3


def test_rejects_oversized_body(client):
    c, _ = client
    body = label_body(uuid4(), label(region="x" * 20_000))
    assert c.post("/v1/labels", json=body, headers=headers()).status_code == 413


def test_delete_install_removes_labels_logs_diagnostics_in_every_mode(client):
    c, root = client
    iid = uuid4()
    c.post("/v1/labels", json=label_body(iid), headers=headers())
    c.post("/v1/labels", json=label_body(iid, mode="dev"), headers=headers())
    c.post("/v1/logs", json=log_body(iid), headers=headers())
    c.post("/v1/diagnostics", json=diag_body(iid), headers=headers())
    assert c.delete(f"/v1/installs/{iid}", headers=headers()).json() == {"deleted": True}
    assert not list(root.rglob(str(iid)))
    assert c.delete(f"/v1/installs/{iid}", headers=headers()).json() == {"deleted": False}
