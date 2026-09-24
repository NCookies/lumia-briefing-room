import base64
import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pull_labels = _load("pull_labels")
eval_pvp = _load("eval_pvp")


def item(clip_key, user_label="combat", received="2026-09-25T10:00:00+00:00", install="3f2b8c1e-5a4d-4e6f-9b7a-1c2d3e4f5a6b", **extra):
    return {
        "installId": install, "receivedAt": received, "appVersion": "0.1.1", "schemaVersion": 1,
        "label": {"userLabel": user_label, "matchKey": "m" * 32, "clipKey": clip_key, "pvpScore": 1.0,
                  "pvpSignals": ["kill_delta"], "sourceWidth": 2560, "sourceHeight": 1440, **extra},
    }


def cursor_of(entry):
    key = [entry["receivedAt"], entry["installId"], entry["label"]["clipKey"]]
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


class FakeServer:
    """관리자 API 흉내. items 를 페이지 크기만큼 잘라 next·cursor 를 준다."""

    def __init__(self, items, page=2, admin="adm"):
        self.items, self.page, self.admin = items, page, admin
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if request.headers.get("x-admin-token") != self.admin:
            return httpx.Response(401, json={"detail": "invalid token"})
        after = request.url.params.get("after")
        start = 0
        if after:
            start = next((i + 1 for i, e in enumerate(self.items) if cursor_of(e) == after), 0)
        chunk = self.items[start:start + self.page]
        more = start + self.page < len(self.items)
        last = cursor_of(chunk[-1]) if chunk else None
        return httpx.Response(200, json={"labels": chunk, "next": last if more else None, "cursor": last})


def client(server):
    return httpx.Client(base_url="https://r.example", transport=httpx.MockTransport(server),
                        headers={"X-Admin-Token": server.admin})


def test_pulls_every_page_and_writes_labels_in_the_local_archive_format(tmp_path):
    server = FakeServer([item("a" * 32), item("b" * 32, "other"), item("c" * 32)])
    result = pull_labels.pull(client(server), tmp_path, mode="release")
    assert result.count == 3 and result.combat == 2 and result.other == 1 and result.installs == 1
    written = sorted(p.name for p in (tmp_path / ".labels").glob("*.json"))
    assert written == [f"{k * 32}.json" for k in "abc"]
    data = json.loads((tmp_path / ".labels" / f"{'b' * 32}.json").read_text(encoding="utf-8"))
    assert data["userLabel"] == "pve" and data["id"] == "b" * 32 and data["installId"].startswith("3f2b")


def test_combat_and_other_become_the_local_pvp_and_pve_values(tmp_path):
    server = FakeServer([item("a" * 32, "combat"), item("b" * 32, "other")])
    pull_labels.pull(client(server), tmp_path, mode="release")
    labels = {p.stem: json.loads(p.read_text(encoding="utf-8"))["userLabel"] for p in (tmp_path / ".labels").glob("*.json")}
    assert labels == {"a" * 32: "pvp", "b" * 32: "pve"}


def test_output_is_readable_by_eval_pvp_unchanged(tmp_path):
    server = FakeServer([item("a" * 32, "combat"), item("b" * 32, "other", pvpScore=0.0, pvpSignals=[])])
    pull_labels.pull(client(server), tmp_path, mode="release")
    clips = eval_pvp.load_clips(tmp_path)
    report = eval_pvp.evaluate_labels(clips)
    assert report["labeled"] == 2 and report["pvp"] == 1 and report["pve"] == 1


def test_second_run_fetches_only_what_is_new_using_the_saved_cursor(tmp_path):
    items = [item("a" * 32), item("b" * 32)]
    server = FakeServer(items, page=10)
    pull_labels.pull(client(server), tmp_path, mode="release")
    items.append(item("c" * 32, received="2026-09-26T10:00:00+00:00"))
    server.requests.clear()
    result = pull_labels.pull(client(server), tmp_path, mode="release")
    assert result.count == 1 and (tmp_path / ".labels" / f"{'c' * 32}.json").exists()
    assert "after" in server.requests[0].url.params


def test_full_ignores_the_saved_cursor(tmp_path):
    server = FakeServer([item("a" * 32)], page=10)
    pull_labels.pull(client(server), tmp_path, mode="release")
    server.requests.clear()
    result = pull_labels.pull(client(server), tmp_path, mode="release", full=True)
    assert result.count == 1 and "after" not in server.requests[0].url.params


def test_a_relabeled_clip_overwrites_the_same_file(tmp_path):
    items = [item("a" * 32, "combat")]
    server = FakeServer(items, page=10)
    pull_labels.pull(client(server), tmp_path, mode="release")
    items.append(item("a" * 32, "other", received="2026-09-26T10:00:00+00:00"))
    pull_labels.pull(client(server), tmp_path, mode="release")
    (path,) = list((tmp_path / ".labels").glob("*.json"))
    assert json.loads(path.read_text(encoding="utf-8"))["userLabel"] == "pve"


def test_dev_and_release_pulls_do_not_share_a_cursor_or_folder(tmp_path):
    server = FakeServer([item("a" * 32)], page=10)
    pull_labels.pull(client(server), tmp_path, mode="release")
    server.requests.clear()
    pull_labels.pull(client(server), tmp_path, mode="dev")
    assert "after" not in server.requests[0].url.params and server.requests[0].url.params["mode"] == "dev"
    assert (tmp_path / "dev" / ".labels").exists()


def test_wrong_admin_token_is_a_clear_error(tmp_path):
    server = FakeServer([item("a" * 32)])
    bad = httpx.Client(base_url="https://r.example", transport=httpx.MockTransport(server), headers={"X-Admin-Token": "nope"})
    with pytest.raises(pull_labels.PullError, match="관리자 토큰"):
        pull_labels.pull(bad, tmp_path, mode="release")


def test_disabled_admin_api_is_a_clear_error(tmp_path):
    disabled = httpx.Client(base_url="https://r.example", headers={"X-Admin-Token": "x"},
                            transport=httpx.MockTransport(lambda r: httpx.Response(404, json={"detail": "not found"})))
    with pytest.raises(pull_labels.PullError, match="꺼져"):
        pull_labels.pull(disabled, tmp_path, mode="release")


def test_network_failure_is_a_clear_error_and_keeps_what_was_already_written(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"labels": [item("a" * 32)], "next": "x", "cursor": "x"})
        raise httpx.ConnectError("down")

    flaky = httpx.Client(base_url="https://r.example", transport=httpx.MockTransport(handler), headers={"X-Admin-Token": "x"})
    with pytest.raises(pull_labels.PullError, match="연결"):
        pull_labels.pull(flaky, tmp_path, mode="release")
    assert (tmp_path / ".labels" / f"{'a' * 32}.json").exists()


def test_token_comes_from_the_environment_and_is_never_printed(tmp_path, monkeypatch, capsys):
    server = FakeServer([item("a" * 32)], admin="super-secret-admin")
    monkeypatch.setenv("LUMIA_ADMIN_TOKEN", "super-secret-admin")
    code = pull_labels.main(["--out", str(tmp_path)], transport=httpx.MockTransport(server))
    out = capsys.readouterr()
    assert code == 0 and "super-secret-admin" not in out.out + out.err and "eval_pvp.py" in out.out


def test_missing_token_stops_with_a_hint(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LUMIA_ADMIN_TOKEN", raising=False)
    code = pull_labels.main(["--out", str(tmp_path)])
    assert code == 2 and "LUMIA_ADMIN_TOKEN" in capsys.readouterr().err
