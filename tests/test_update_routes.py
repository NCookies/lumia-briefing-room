import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, dataclass_from_camel_dict, save_config
from lumia_briefing_room.updater import Updater
from tests.test_updater import CURRENT, INSTALLER_BYTES, NEW, FakeGitHub


@pytest.fixture
def github():
    server = FakeGitHub()
    yield server
    server.close()


@pytest.fixture
def client(tmp_path, github):
    config_path = tmp_path / "config.json"
    save_config(dataclass_from_camel_dict(Config, {"update": {"check": False}}), config_path)
    launched = []
    quit_calls = []
    updater = Updater(
        config_path=config_path, state_path=tmp_path / "state.json", download_dir=tmp_path / "updates",
        current_version=CURRENT, api_url=github.api_url, download_prefix=github.download_prefix,
        launcher=launched.append, on_launched=lambda: quit_calls.append(1),
    )
    app = create_app(Config(), config_path=config_path)
    app.state.updater = updater
    test_client = TestClient(app)
    test_client.launched = launched
    test_client.quit_calls = quit_calls
    test_client.updater = updater
    return test_client


def test_status_reports_disabled_auto_check_without_network(client, github):
    body = client.get("/api/update/status").json()
    assert body["enabled"] is False
    assert body["available"] is None
    assert body["current"] == CURRENT
    assert github.hits == []


def test_manual_check_reports_new_version_even_when_auto_check_is_off(client, github):
    github.publish(NEW)
    body = client.post("/api/update/check").json()
    assert body["state"] == "available"
    assert body["release"]["version"] == NEW


def test_manual_check_reports_latest(client, github):
    github.publish(CURRENT)
    assert client.post("/api/update/check").json()["state"] == "latest"


def test_manual_check_error_is_a_normal_response(client, github):
    github.routes["/repos/o/r/releases/latest"] = (500, b"")
    body = client.post("/api/update/check").json()
    assert body["state"] == "error"
    assert body["error"]


def test_install_runs_in_background_and_reports_progress(client, github):
    github.publish(NEW)
    assert client.post("/api/update/install").status_code == 202
    client.updater.wait_install(timeout=10)
    body = client.get("/api/update/status").json()
    assert body["install"]["state"] == "launched"
    assert client.launched[0].read_bytes() == INSTALLER_BYTES
    assert client.quit_calls == [1]


def test_install_refuses_bad_checksum(client, github):
    github.publish(NEW, checksum="f" * 64)
    client.post("/api/update/install")
    client.updater.wait_install(timeout=10)
    install = client.get("/api/update/status").json()["install"]
    assert install["state"] == "failed"
    assert client.launched == []
