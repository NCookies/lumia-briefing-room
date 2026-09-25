import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room import admin_labels
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import AppConfig, Config

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


def make(items=ITEMS, cfg=None, **kw):
    server = FakeServer(items, **kw)
    client = httpx.Client(base_url="https://r.example", headers={"X-Admin-Token": "adm"}, transport=httpx.MockTransport(server))
    app = create_app(cfg or Config())
    app.state.admin_client = client
    return TestClient(app), server


def test_fetch_all_follows_pages():
    server = FakeServer(ITEMS)
    client = httpx.Client(base_url="https://r.example", headers={"X-Admin-Token": "adm"}, transport=httpx.MockTransport(server))
    assert [i["label"]["clipKey"] for i in admin_labels.fetch_all(client, "release")] == ["c1", "c2", "c3", "c4", "c5"]
    assert len(server.requests) == 3


def test_summarize_counts():
    s = admin_labels.summarize(ITEMS)
    assert s["total"] == 5
    assert s["installs"] == 2
    assert s["byLabel"] == {"combat": 3, "other": 2}
    assert s["byVersion"] == {"0.1.1": 2, "0.1.2": 3}
    assert s["byResolution"] == {"2560x1440": 2, "1920x1080": 3}
    assert s["byDay"] == {"2026-09-24": 2, "2026-09-25": 3}
    assert s["lastReceivedAt"] == "2026-09-25T13:00:00+00:00"
    assert s["perInstall"][0] == {"installId": B, "count": 3, "combat": 2, "other": 1, "lastReceivedAt": "2026-09-25T13:00:00+00:00"}


def test_summarize_empty():
    s = admin_labels.summarize([])
    assert s["total"] == 0 and s["installs"] == 0 and s["lastReceivedAt"] is None and s["perInstall"] == []


def test_filter_by_install_prefix_or_clip_key_and_label():
    assert [i["label"]["clipKey"] for i in admin_labels.filter_items(ITEMS, q="9a8b")] == ["c3", "c4", "c5"]
    assert [i["label"]["clipKey"] for i in admin_labels.filter_items(ITEMS, q="C2")] == ["c2"]
    assert [i["label"]["clipKey"] for i in admin_labels.filter_items(ITEMS, user_label="other")] == ["c2", "c5"]
    assert len(admin_labels.filter_items(ITEMS)) == 5


def test_summary_endpoint_and_cache():
    c, server = make()
    assert c.get("/api/admin/summary").json()["total"] == 5
    calls = len(server.requests)
    c.get("/api/admin/summary")
    c.get("/api/admin/labels")
    assert len(server.requests) == calls
    c.get("/api/admin/summary?refresh=1")
    assert len(server.requests) == calls * 2


def test_labels_endpoint_search_and_paging():
    c, _ = make()
    body = c.get("/api/admin/labels?q=9a8b&limit=2").json()
    assert body["total"] == 3
    assert [i["label"]["clipKey"] for i in body["items"]] == ["c5", "c4"]
    assert [i["label"]["clipKey"] for i in c.get("/api/admin/labels?q=9a8b&limit=2&offset=2").json()["items"]] == ["c3"]


def test_mode_is_passed_and_cached_separately():
    c, server = make()
    c.get("/api/admin/summary?mode=dev")
    c.get("/api/admin/summary?mode=release")
    assert {r.url.params["mode"] for r in server.requests} == {"dev", "release"}


@pytest.mark.parametrize("status,text", [(401, "토큰"), (404, "꺼져"), (429, "너무 많"), (500, "HTTP 500")])
def test_server_errors_become_502_with_message(status, text):
    c, _ = make(status=status)
    r = c.get("/api/admin/summary")
    assert r.status_code == 502 and text in r.json()["detail"]


def test_release_mode_hides_the_routes_even_with_a_client():
    c, server = make(cfg=Config(app=AppConfig(mode="release")))
    assert c.get("/api/admin/summary").status_code == 404
    assert c.get("/api/admin/labels").status_code == 404
    assert server.requests == []


def test_missing_token_or_url_is_a_503_that_never_echoes_secrets(monkeypatch, tmp_path):
    monkeypatch.delenv("LUMIA_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("LUMIA_RECEIVER_URL", "https://r.example")
    monkeypatch.setattr(admin_labels, "ENV_FILE", tmp_path / "none.env")
    c = TestClient(create_app(Config()))
    r = c.get("/api/admin/summary")
    assert r.status_code == 503 and "LUMIA_ADMIN_TOKEN" in r.json()["detail"]
    monkeypatch.setenv("LUMIA_ADMIN_TOKEN", "adm")
    monkeypatch.delenv("LUMIA_RECEIVER_URL")
    r = c.get("/api/admin/summary")
    assert r.status_code == 503 and "LUMIA_RECEIVER_URL" in r.json()["detail"] and "adm" not in r.text


def test_credentials_come_from_the_env_file_when_not_in_the_environment(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("LUMIA_ADMIN_TOKEN=from-file\nLUMIA_RECEIVER_URL=https://f.example/\n", encoding="utf-8")
    monkeypatch.delenv("LUMIA_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("LUMIA_RECEIVER_URL", raising=False)
    assert admin_labels.read_credentials(env) == ("https://f.example", "from-file")
    assert "LUMIA_ADMIN_TOKEN" not in __import__("os").environ


def test_a_token_that_cannot_be_a_header_is_a_503_not_a_crash(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("LUMIA_ADMIN_TOKEN=abc주석\nLUMIA_RECEIVER_URL=https://r.example\n", encoding="utf-8")
    monkeypatch.delenv("LUMIA_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("LUMIA_RECEIVER_URL", raising=False)
    monkeypatch.setattr(admin_labels, "ENV_FILE", env)
    r = TestClient(create_app(Config())).get("/api/admin/summary")
    assert r.status_code == 503 and "LUMIA_ADMIN_TOKEN" in r.json()["detail"] and "abc" not in r.text
