import base64
import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


admin_dashboard = _load("admin_dashboard")

A = "3f2b8c1e-5a4d-4e6f-9b7a-1c2d3e4f5a6b"
B = "9a8b7c6d-1111-4222-8333-444455556666"


def item(clip_key, user_label="combat", received="2026-09-25T10:00:00+00:00", install=A, version="0.1.1", width=2560, height=1440):
    return {
        "installId": install, "receivedAt": received, "appVersion": version, "schemaVersion": 1,
        "label": {"userLabel": user_label, "matchKey": "m" * 32, "clipKey": clip_key, "sourceWidth": width, "sourceHeight": height},
    }


def cursor_of(entry):
    key = [entry["receivedAt"], entry["installId"], entry["label"]["clipKey"]]
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


class FakeServer:
    def __init__(self, items, page=2, admin="adm", status=200):
        self.items, self.page, self.admin, self.status = items, page, admin, status
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={})
        if request.headers.get("x-admin-token") != self.admin:
            return httpx.Response(401, json={})
        after = request.url.params.get("after")
        start = 0
        if after:
            start = next((i + 1 for i, e in enumerate(self.items) if cursor_of(e) == after), 0)
        chunk = self.items[start:start + self.page]
        more = start + self.page < len(self.items)
        last = cursor_of(chunk[-1]) if chunk else None
        return httpx.Response(200, json={"labels": chunk, "next": last if more else None, "cursor": last})


ITEMS = [
    item("c1", "combat", "2026-09-24T10:00:00+00:00", A, "0.1.1"),
    item("c2", "other", "2026-09-24T12:00:00+00:00", A, "0.1.1"),
    item("c3", "combat", "2026-09-25T09:00:00+00:00", B, "0.1.2", 1920, 1080),
    item("c4", "combat", "2026-09-25T11:00:00+00:00", B, "0.1.2", 1920, 1080),
    item("c5", "other", "2026-09-25T13:00:00+00:00", B, "0.1.2", 1920, 1080),
]


def make(items=ITEMS, **kw):
    server = FakeServer(items, **kw)
    client = httpx.Client(base_url="https://r.example", headers={"X-Admin-Token": "adm"}, transport=httpx.MockTransport(server))
    return TestClient(admin_dashboard.create_app(client)), server


def test_fetch_all_follows_pages():
    server = FakeServer(ITEMS)
    client = httpx.Client(base_url="https://r.example", headers={"X-Admin-Token": "adm"}, transport=httpx.MockTransport(server))
    assert [i["label"]["clipKey"] for i in admin_dashboard.fetch_all(client, "release")] == ["c1", "c2", "c3", "c4", "c5"]
    assert len(server.requests) == 3


def test_summarize_counts():
    s = admin_dashboard.summarize(ITEMS)
    assert s["total"] == 5
    assert s["installs"] == 2
    assert s["byLabel"] == {"combat": 3, "other": 2}
    assert s["byVersion"] == {"0.1.1": 2, "0.1.2": 3}
    assert s["byResolution"] == {"2560x1440": 2, "1920x1080": 3}
    assert s["byDay"] == {"2026-09-24": 2, "2026-09-25": 3}
    assert s["lastReceivedAt"] == "2026-09-25T13:00:00+00:00"
    assert s["perInstall"][0] == {"installId": B, "count": 3, "combat": 2, "other": 1, "lastReceivedAt": "2026-09-25T13:00:00+00:00"}


def test_summarize_empty():
    s = admin_dashboard.summarize([])
    assert s["total"] == 0 and s["installs"] == 0 and s["lastReceivedAt"] is None and s["perInstall"] == []


def test_filter_by_install_prefix_or_clip_key_and_label():
    assert [i["label"]["clipKey"] for i in admin_dashboard.filter_items(ITEMS, q="9a8b")] == ["c3", "c4", "c5"]
    assert [i["label"]["clipKey"] for i in admin_dashboard.filter_items(ITEMS, q="C2")] == ["c2"]
    assert [i["label"]["clipKey"] for i in admin_dashboard.filter_items(ITEMS, user_label="other")] == ["c2", "c5"]
    assert len(admin_dashboard.filter_items(ITEMS)) == 5


def test_summary_endpoint_and_cache():
    c, server = make()
    assert c.get("/api/summary").json()["total"] == 5
    calls = len(server.requests)
    c.get("/api/summary")
    c.get("/api/labels")
    assert len(server.requests) == calls
    c.get("/api/summary?refresh=1")
    assert len(server.requests) == calls * 2


def test_labels_endpoint_search_and_paging():
    c, _ = make()
    body = c.get("/api/labels?q=9a8b&limit=2").json()
    assert body["total"] == 3
    assert [i["label"]["clipKey"] for i in body["items"]] == ["c5", "c4"]
    assert [i["label"]["clipKey"] for i in c.get("/api/labels?q=9a8b&limit=2&offset=2").json()["items"]] == ["c3"]


def test_mode_is_passed_and_cached_separately():
    c, server = make()
    c.get("/api/summary?mode=dev")
    c.get("/api/summary?mode=release")
    assert {r.url.params["mode"] for r in server.requests} == {"dev", "release"}


@pytest.mark.parametrize("status,text", [(401, "토큰"), (404, "꺼져"), (429, "너무 많"), (500, "HTTP 500")])
def test_server_errors_become_502_with_message(status, text):
    c, _ = make(status=status)
    r = c.get("/api/summary")
    assert r.status_code == 502 and text in r.json()["detail"]


def test_index_page_served_without_token():
    c, _ = make()
    r = c.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "adm" not in r.text


def test_main_requires_token_and_url(monkeypatch, capsys):
    monkeypatch.delenv("LUMIA_ADMIN_TOKEN", raising=False)
    assert admin_dashboard.main(["--url", "https://r.example", "--no-open"]) == 2
    monkeypatch.setenv("LUMIA_ADMIN_TOKEN", "adm")
    monkeypatch.delenv("LUMIA_RECEIVER_URL", raising=False)
    assert admin_dashboard.main(["--no-open"]) == 2
    assert "adm" not in capsys.readouterr().err
