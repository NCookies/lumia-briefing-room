import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.test_api import TOKEN, headers, label, label_body

ADMIN = "admin-secret"


def admin(token=ADMIN):
    return {"X-Admin-Token": token}


def make_client(tmp_path, admin_token=ADMIN):
    settings = Settings(data_dir=tmp_path, api_tokens=(TOKEN,), max_body_bytes=100_000, admin_token=admin_token)
    return TestClient(create_app(settings))


def upload(c, install_id, *labels, mode="release"):
    r = c.post("/v1/labels", json=label_body(install_id, *labels, mode=mode), headers=headers())
    assert r.status_code == 200


def test_admin_export_is_disabled_when_no_admin_token_is_configured(tmp_path):
    c = make_client(tmp_path, admin_token="")
    assert c.get("/v1/admin/labels", headers=admin("")).status_code == 404


def test_admin_export_needs_the_admin_token_not_the_upload_token(tmp_path):
    c = make_client(tmp_path)
    assert c.get("/v1/admin/labels").status_code == 401
    assert c.get("/v1/admin/labels", headers=admin("nope")).status_code == 401
    assert c.get("/v1/admin/labels", headers={"X-Api-Token": TOKEN}).status_code == 401
    assert c.get("/v1/admin/labels", headers=admin()).status_code == 200


def test_upload_token_cannot_be_used_as_admin_token_even_if_equal_prefix(tmp_path):
    c = make_client(tmp_path)
    assert c.get("/v1/admin/labels", headers=admin(TOKEN)).status_code == 401


def test_exports_uploaded_labels_with_install_id_and_metadata(tmp_path):
    c = make_client(tmp_path)
    iid = uuid4()
    upload(c, iid, label(clip_key="c" * 32, labelNote="메모", killDelta=2))
    body = c.get("/v1/admin/labels", headers=admin()).json()
    assert body["next"] is None and len(body["labels"]) == 1
    (item,) = body["labels"]
    assert item["installId"] == str(iid) and item["appVersion"] == "0.1.0" and item["schemaVersion"] == 1
    assert item["label"]["userLabel"] == "combat" and item["label"]["labelNote"] == "메모"
    assert item["label"]["clipKey"] == "c" * 32 and item["receivedAt"]


def test_release_and_dev_data_are_kept_apart(tmp_path):
    c = make_client(tmp_path)
    upload(c, uuid4(), label(clip_key="a" * 32))
    upload(c, uuid4(), label(clip_key="b" * 32), mode="dev")
    release = c.get("/v1/admin/labels", headers=admin()).json()["labels"]
    dev = c.get("/v1/admin/labels?mode=dev", headers=admin()).json()["labels"]
    assert [i["label"]["clipKey"] for i in release] == ["a" * 32]
    assert [i["label"]["clipKey"] for i in dev] == ["b" * 32]
    assert c.get("/v1/admin/labels?mode=staging", headers=admin()).status_code == 422


def test_pagination_walks_every_label_exactly_once_even_with_equal_timestamps(tmp_path):
    c = make_client(tmp_path)
    iid = uuid4()
    keys = [f"{i:032x}" for i in range(7)]
    upload(c, iid, *[label(clip_key=k) for k in keys])
    seen, cursor = [], None
    for _ in range(10):
        url = "/v1/admin/labels?limit=3" + (f"&after={cursor}" if cursor else "")
        page = c.get(url, headers=admin()).json()
        seen += [i["label"]["clipKey"] for i in page["labels"]]
        cursor = page["next"]
        if cursor is None:
            break
    assert sorted(seen) == keys and len(seen) == len(set(seen))


def test_limit_is_capped(tmp_path):
    c = make_client(tmp_path)
    assert c.get("/v1/admin/labels?limit=100000", headers=admin()).status_code == 422


def test_export_never_returns_logs_or_diagnostics(tmp_path):
    c = make_client(tmp_path)
    iid = uuid4()
    body = {"installId": str(iid), "schemaVersion": 1, "mode": "release",
            "env": {"appVersion": "0.1.0", "os": "Windows 11"},
            "entries": [{"ts": "2026-09-24T10:00:00", "level": "ERROR", "message": "boom"}]}
    c.post("/v1/logs", json=body, headers=headers())
    assert c.get("/v1/admin/labels", headers=admin()).json()["labels"] == []


def test_bad_admin_attempts_count_toward_the_rate_limit(tmp_path):
    settings = Settings(data_dir=tmp_path, api_tokens=(TOKEN,), max_body_bytes=1000, admin_token=ADMIN,
                        rate_limit_failures=3)
    c = TestClient(create_app(settings))
    for _ in range(3):
        c.get("/v1/admin/labels", headers=admin("nope"))
    assert c.get("/v1/admin/labels", headers=admin()).status_code == 429
