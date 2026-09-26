from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.test_api import TOKEN, headers, label, label_body

ADMIN = "admin-secret"
FP1, FP2 = "a" * 16, "b" * 16


def admin(token=ADMIN):
    return {"X-Admin-Token": token}


def make_client(tmp_path, admin_token=ADMIN):
    settings = Settings(data_dir=tmp_path, api_tokens=(TOKEN,), max_body_bytes=100_000, admin_token=admin_token)
    return TestClient(create_app(settings))


def entry(message="boom", level="ERROR", ts="2026-09-24T10:00:00", **extra):
    return {"ts": ts, "level": level, "message": message, **extra}


def send(c, path, install_id, entries, *, mode="release", display="LUMIA-7K3F-9QX2", version="0.1.4"):
    body = {
        "installId": str(install_id), "schemaVersion": 1, "mode": mode,
        "env": {"appVersion": version, "os": "Windows 11", "resolution": "1920x1080"},
        "entries": entries,
    }
    if path == "diagnostics":
        body["displayId"] = display
    r = c.post(f"/v1/{path}", json=body, headers=headers())
    assert r.status_code == 200, r.text
    return r.json()


READ_PATHS = ["/v1/admin/status", "/v1/admin/diagnostics", "/v1/admin/diagnostics/R-20260925-ABC234", "/v1/admin/logs", "/v1/admin/logs/groups"]


@pytest.mark.parametrize("path", READ_PATHS)
def test_read_apis_are_off_without_admin_token_and_need_the_admin_token_not_the_upload_token(tmp_path, path):
    assert make_client(tmp_path, admin_token="").get(path, headers=admin("")).status_code == 404
    c = make_client(tmp_path)
    assert c.get(path).status_code == 401
    assert c.get(path, headers={"X-Api-Token": TOKEN}).status_code == 401
    assert c.get(path, headers=admin("nope")).status_code == 401


def test_diagnostics_list_newest_first_with_summary_and_search(tmp_path):
    c = make_client(tmp_path)
    a, b = uuid4(), uuid4()
    r1 = send(c, "diagnostics", a, [entry(), entry(level="WARNING")], display="LUMIA-AAAA-1111")["receiptId"]
    r2 = send(c, "diagnostics", b, [entry()], display="LUMIA-BBBB-2222", version="0.1.5")["receiptId"]
    body = c.get("/v1/admin/diagnostics", headers=admin()).json()
    assert body["total"] == 2
    assert [i["receiptId"] for i in body["items"]] == [r2, r1]
    first = body["items"][1]
    assert first["installId"] == str(a) and first["displayId"] == "LUMIA-AAAA-1111" and first["entryCount"] == 2
    assert first["errorCount"] == 1 and first["appVersion"] == "0.1.4" and first["os"] == "Windows 11" and first["receivedAt"]
    assert "entries" not in first
    for q in (r1, r1.lower(), "LUMIA-AAAA", "lumia-aaaa-1111", str(a)[:8]):
        assert [i["receiptId"] for i in c.get("/v1/admin/diagnostics", params={"q": q}, headers=admin()).json()["items"]] == [r1]
    paged = c.get("/v1/admin/diagnostics", params={"limit": 1, "offset": 1}, headers=admin()).json()
    assert paged["total"] == 2 and [i["receiptId"] for i in paged["items"]] == [r1]


def test_diagnostic_detail_returns_the_full_bundle_and_rejects_bad_ids(tmp_path):
    c = make_client(tmp_path)
    iid = uuid4()
    receipt = send(c, "diagnostics", iid, [entry("stack here", exceptionType="ValueError")])["receiptId"]
    body = c.get(f"/v1/admin/diagnostics/{receipt}", headers=admin()).json()
    assert body["receiptId"] == receipt and body["installId"] == str(iid)
    assert body["env"]["os"] == "Windows 11" and body["entries"][0]["exceptionType"] == "ValueError"
    assert c.get("/v1/admin/diagnostics/R-20260101-ZZZZZZ", headers=admin()).status_code == 404
    for bad in ("..%2F..%2Fetc", "not-a-receipt", "R-1-2"):
        assert c.get(f"/v1/admin/diagnostics/{bad}", headers=admin()).status_code in (404, 422)


def test_diagnostics_are_separated_by_mode(tmp_path):
    c = make_client(tmp_path)
    receipt = send(c, "diagnostics", uuid4(), [entry()], mode="dev")["receiptId"]
    assert c.get("/v1/admin/diagnostics", headers=admin()).json()["total"] == 0
    assert c.get("/v1/admin/diagnostics", params={"mode": "dev"}, headers=admin()).json()["total"] == 1
    assert c.get(f"/v1/admin/diagnostics/{receipt}", headers=admin()).status_code == 404
    assert c.get(f"/v1/admin/diagnostics/{receipt}", params={"mode": "dev"}, headers=admin()).status_code == 200
    assert c.get("/v1/admin/diagnostics", params={"mode": "staging"}, headers=admin()).status_code == 422


def test_logs_are_flattened_newest_first_and_filterable(tmp_path):
    c = make_client(tmp_path)
    a, b = uuid4(), uuid4()
    send(c, "logs", a, [entry("old", ts="2026-09-24T09:00:00"), entry("mid", level="WARNING", ts="2026-09-24T10:00:00")])
    send(c, "logs", b, [entry("new disk full", ts="2026-09-25T08:00:00", exceptionType="OSError", fingerprint=FP1)], version="0.1.5")
    body = c.get("/v1/admin/logs", headers=admin()).json()
    assert body["total"] == 3 and [e["message"] for e in body["items"]] == ["new disk full", "mid", "old"]
    top = body["items"][0]
    assert top["installId"] == str(b) and top["appVersion"] == "0.1.5" and top["exceptionType"] == "OSError" and top["fingerprint"] == FP1
    assert top["receivedAt"] and top["level"] == "ERROR"
    only_a = c.get("/v1/admin/logs", params={"installId": str(a)}, headers=admin()).json()
    assert [e["message"] for e in only_a["items"]] == ["mid", "old"]
    assert [e["message"] for e in c.get("/v1/admin/logs", params={"level": "WARNING"}, headers=admin()).json()["items"]] == ["mid"]
    assert [e["message"] for e in c.get("/v1/admin/logs", params={"q": "DISK"}, headers=admin()).json()["items"]] == ["new disk full"]
    paged = c.get("/v1/admin/logs", params={"limit": 1, "offset": 1}, headers=admin()).json()
    assert paged["total"] == 3 and [e["message"] for e in paged["items"]] == ["mid"]


def test_log_groups_count_by_fingerprint_with_installs_and_last_seen(tmp_path):
    c = make_client(tmp_path)
    a, b = uuid4(), uuid4()
    send(c, "logs", a, [entry("disk full A", ts="2026-09-24T09:00:00", fingerprint=FP1, exceptionType="OSError"),
                        entry("disk full A", ts="2026-09-24T11:00:00", fingerprint=FP1, exceptionType="OSError")])
    send(c, "logs", b, [entry("disk full B", ts="2026-09-25T08:00:00", fingerprint=FP1, exceptionType="OSError"),
                        entry("other", level="WARNING", ts="2026-09-25T09:00:00", fingerprint=FP2)])
    groups = c.get("/v1/admin/logs/groups", headers=admin()).json()["groups"]
    assert [g["fingerprint"] for g in groups] == [FP1, FP2]
    g = groups[0]
    assert g["count"] == 3 and g["installs"] == 2 and g["level"] == "ERROR" and g["exceptionType"] == "OSError"
    assert g["firstSeen"] == "2026-09-24T09:00:00" and g["lastSeen"] == "2026-09-25T08:00:00" and g["message"].startswith("disk full")
    assert groups[1]["count"] == 1 and groups[1]["level"] == "WARNING"


def test_log_groups_fall_back_to_type_and_message_when_no_fingerprint(tmp_path):
    c = make_client(tmp_path)
    send(c, "logs", uuid4(), [entry("same", exceptionType="E"), entry("same", exceptionType="E"), entry("different")])
    groups = c.get("/v1/admin/logs/groups", headers=admin()).json()["groups"]
    assert sorted(g["count"] for g in groups) == [1, 2]
    assert all(g["fingerprint"] is None for g in groups)


def test_logs_are_separated_by_mode(tmp_path):
    c = make_client(tmp_path)
    send(c, "logs", uuid4(), [entry("dev only")], mode="dev")
    assert c.get("/v1/admin/logs", headers=admin()).json()["total"] == 0
    assert c.get("/v1/admin/logs", params={"mode": "dev"}, headers=admin()).json()["total"] == 1
    assert c.get("/v1/admin/logs/groups", headers=admin()).json()["groups"] == []


def test_status_reports_counts_last_received_disk_and_todays_requests(tmp_path):
    c = make_client(tmp_path)
    empty = c.get("/v1/admin/status", headers=admin()).json()
    assert empty["release"]["labels"] == 0 and empty["release"]["lastReceived"] == {"labels": None, "logs": None, "diagnostics": None}
    iid = uuid4()
    assert c.post("/v1/labels", json=label_body(iid, label(clip_key="c" * 32), label(clip_key="d" * 32)), headers=headers()).status_code == 200
    send(c, "logs", iid, [entry()])
    send(c, "diagnostics", iid, [entry()])
    send(c, "diagnostics", uuid4(), [entry()], mode="dev")
    s = c.get("/v1/admin/status", headers=admin()).json()
    assert s["release"]["labels"] == 2 and s["release"]["installs"] == 1
    assert s["release"]["logEntryFiles"] == 1 and s["release"]["diagnostics"] == 1 and s["dev"]["diagnostics"] == 1
    assert all(s["release"]["lastReceived"][k] for k in ("labels", "logs", "diagnostics")) and s["dev"]["lastReceived"]["labels"] is None
    assert s["today"]["requests"] == {"labels": 1, "logs": 1, "diagnostics": 2}
    assert s["disk"]["totalBytes"] > 0 and 0 <= s["disk"]["usedPercent"] <= 100 and s["disk"]["dataBytes"] > 0
    assert s["blockedIps"] == 0 and s["retentionDays"] == 90 and s["serverTime"]
    assert "192." not in str(s)


def test_rate_limiter_counts_currently_blocked_ips():
    from app.ratelimit import RateLimiter

    now = [0.0]
    limiter = RateLimiter(window_sec=60, max_requests=100, max_failures=2, block_sec=100, clock=lambda: now[0])
    assert limiter.blocked_count() == 0
    limiter.record_failure("1.1.1.1")
    limiter.record_failure("1.1.1.1")
    limiter.record_failure("2.2.2.2")
    assert limiter.blocked_count() == 1
    now[0] = 101.0
    assert limiter.blocked_count() == 0
