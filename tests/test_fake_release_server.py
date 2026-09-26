import hashlib
import json
import sys
import threading
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fake_release_server as fake  # noqa: E402

from lumia_briefing_room.config import Config, dataclass_from_camel_dict, save_config  # noqa: E402
from lumia_briefing_room.updater import Updater  # noqa: E402

INSTALLER = b"MZ-test-installer-" * 5000


@pytest.fixture
def served(tmp_path):
    installer = tmp_path / "LumiaBriefingRoom-0.1.3-setup.exe"
    installer.write_bytes(INSTALLER)
    routes: dict = {}
    server = fake.make_server(routes, 0)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    routes.update(fake.build_routes(installer, "9.9.9", base, "### 시험\n- 항목 하나\n"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield base, installer
    server.shutdown()
    server.server_close()


def test_the_fake_server_speaks_the_github_release_shape(served):
    base, installer = served
    release = httpx.get(f"{base}{fake.API_PATH}").json()
    assert release["tag_name"] == "v9.9.9" and release["draft"] is False and release["prerelease"] is False
    assert release["body"].startswith("### 시험")
    names = [a["name"] for a in release["assets"]]
    assert names == [installer.name, installer.name + ".sha256"]
    checksum = httpx.get(release["assets"][1]["browser_download_url"]).text
    assert checksum == f"{hashlib.sha256(INSTALLER).hexdigest()} *{installer.name}\n"
    assert httpx.get(release["assets"][0]["browser_download_url"]).content == INSTALLER
    assert httpx.get(f"{base}/nope").status_code == 404


def test_the_app_updates_end_to_end_against_the_fake_server(served, tmp_path):
    base, installer = served
    config_path = tmp_path / "config.json"
    save_config(dataclass_from_camel_dict(Config, {"update": {"check": False}}), config_path)
    launched: list = []
    updater = Updater(
        config_path=config_path, state_path=tmp_path / "s.json", download_dir=tmp_path / "updates",
        current_version="0.1.3", api_url=f"{base}{fake.API_PATH}", download_prefix=f"{base}{fake.DOWNLOAD_PATH}",
        launcher=launched.append,
    )

    result = updater.check()
    assert result["state"] == "available" and result["release"]["version"] == "9.9.9"
    updater.install_sync()

    assert updater.status()["install"]["state"] == "launched"
    assert launched[0].read_bytes() == INSTALLER


def test_the_tool_refuses_a_file_that_is_not_an_installer(tmp_path, capsys):
    other = tmp_path / "notes.txt"
    other.write_text("x", encoding="utf-8")
    assert fake.main([str(other), "--version", "9.9.9"]) == 2
    assert "설치기" in capsys.readouterr().err
