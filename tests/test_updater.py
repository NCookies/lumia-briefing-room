import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lumia_briefing_room import procs
from lumia_briefing_room.config import Config, dataclass_from_camel_dict, save_config
from lumia_briefing_room.updater import (
    CHECK_INTERVAL,
    RETRY_INTERVAL,
    Updater,
    installer_command,
    is_newer,
    parse_version,
)

CURRENT = "0.1.3"
NEW = "0.2.0"
INSTALLER_BYTES = b"MZ-fake-installer-" * 1000


class FakeGitHub:
    """GitHub Releases API 와 릴리스 파일 서버를 한 로컬 HTTP 서버로 흉내 낸다."""

    def __init__(self):
        self.routes: dict[str, tuple[int, bytes]] = {}
        self.hits: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.hits.append(self.path)
                status, body = outer.routes.get(self.path, (404, b"not found"))
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def api_url(self):
        return f"{self.base}/repos/o/r/releases/latest"

    @property
    def download_prefix(self):
        return f"{self.base}/o/r/releases/download/"

    def publish(self, version=NEW, *, installer=INSTALLER_BYTES, checksum=None, with_sha=True, **release_extra):
        name = f"LumiaBriefingRoom-{version}-setup.exe"
        digest = checksum or hashlib.sha256(installer).hexdigest()
        prefix = f"/o/r/releases/download/v{version}"
        assets = [{"name": name, "browser_download_url": f"{self.base}{prefix}/{name}"}]
        self.routes[f"{prefix}/{name}"] = (200, installer)
        if with_sha:
            assets.append({"name": f"{name}.sha256", "browser_download_url": f"{self.base}{prefix}/{name}.sha256"})
            self.routes[f"{prefix}/{name}.sha256"] = (200, f"{digest} *{name}\n".encode())
        payload = {"tag_name": f"v{version}", "name": f"v{version}", "draft": False, "prerelease": False,
                   "body": "패치노트 본문", "html_url": f"https://example.invalid/v{version}", "assets": assets}
        payload.update(release_extra)
        self.routes["/repos/o/r/releases/latest"] = (200, json.dumps(payload).encode())

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def github():
    server = FakeGitHub()
    yield server
    server.close()


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Env:
    def __init__(self, tmp_path, github):
        self.github = github
        self.clock = Clock()
        self.config_path = tmp_path / "config.json"
        self.launched: list = []
        self.notified: list = []
        self.quit_calls = 0
        self.set_check(False)
        self.updater = Updater(
            config_path=self.config_path,
            state_path=tmp_path / "update_state.json",
            download_dir=tmp_path / "updates",
            current_version=CURRENT,
            api_url=github.api_url,
            download_prefix=github.download_prefix,
            clock=self.clock,
            launcher=self.launched.append,
            notify=self.notified.append,
            on_launched=self.on_launched,
        )

    def on_launched(self):
        self.quit_calls += 1

    def set_check(self, value):
        save_config(dataclass_from_camel_dict(Config, {"update": {"check": value}}), self.config_path)


@pytest.fixture
def env(tmp_path, github):
    return Env(tmp_path, github)


def test_versions_compare_numerically():
    assert parse_version("v0.1.10") == (0, 1, 10)
    assert parse_version("0.2.0") == (0, 2, 0)
    assert parse_version("0.2.0-beta") is None
    assert parse_version("최신") is None
    assert is_newer("0.1.10", "0.1.9")
    assert not is_newer("0.1.3", "0.1.3")
    assert not is_newer("0.1.2", "0.1.3")
    assert not is_newer("망가짐", "0.1.3")


def test_check_reports_available_release(env):
    env.github.publish(NEW)
    result = env.updater.check()
    assert result["state"] == "available"
    assert result["current"] == CURRENT
    assert result["release"]["version"] == NEW
    assert result["release"]["notes"] == "패치노트 본문"


@pytest.mark.parametrize("latest", [CURRENT, "0.1.2"])
def test_check_reports_latest_when_not_newer(env, latest):
    env.github.publish(latest)
    assert env.updater.check()["state"] == "latest"


def test_draft_and_prerelease_are_not_offered(env):
    env.github.publish(NEW, prerelease=True)
    assert env.updater.check()["state"] == "latest"
    env.github.publish(NEW, draft=True)
    assert env.updater.check()["state"] == "latest"


def test_release_without_checksum_is_not_offered(env):
    env.github.publish(NEW, with_sha=False)
    result = env.updater.check()
    assert result["state"] == "error"
    assert "체크섬" in result["error"]


def test_download_url_outside_release_prefix_is_rejected(env):
    env.github.publish(NEW)
    payload = json.loads(env.github.routes["/repos/o/r/releases/latest"][1])
    payload["assets"][0]["browser_download_url"] = "http://evil.invalid/setup.exe"
    env.github.routes["/repos/o/r/releases/latest"] = (200, json.dumps(payload).encode())
    assert env.updater.check()["state"] == "error"


@pytest.mark.parametrize("status,body", [(500, b"boom"), (404, b"{}"), (200, b"not json"), (200, b"[]")])
def test_check_failures_become_error_state_not_exceptions(env, status, body):
    env.github.routes["/repos/o/r/releases/latest"] = (status, body)
    assert env.updater.check()["state"] == "error"


def test_check_survives_unreachable_server(tmp_path, github):
    env = Env(tmp_path, github)
    github.close()
    assert env.updater.check()["state"] == "error"


def test_auto_check_off_never_touches_network(env):
    env.github.publish(NEW)
    assert env.updater.maybe_auto_check() is None
    assert env.github.hits == []
    assert env.notified == []


def test_manual_check_works_while_auto_check_is_off(env):
    env.github.publish(NEW)
    assert env.updater.check()["state"] == "available"
    assert len(env.github.hits) == 1
    assert env.notified == []


def test_auto_check_runs_at_most_once_a_day(env):
    env.set_check(True)
    env.github.publish(CURRENT)
    assert env.updater.maybe_auto_check()["state"] == "latest"
    assert env.updater.maybe_auto_check() is None
    env.clock.advance(CHECK_INTERVAL - 60)
    assert env.updater.maybe_auto_check() is None
    env.clock.advance(120)
    assert env.updater.maybe_auto_check() is not None
    assert len(env.github.hits) == 2


def test_auto_check_retries_sooner_after_failure(env):
    env.set_check(True)
    env.github.routes["/repos/o/r/releases/latest"] = (500, b"")
    assert env.updater.maybe_auto_check()["state"] == "error"
    assert env.updater.maybe_auto_check() is None
    env.clock.advance(RETRY_INTERVAL + 1)
    env.github.publish(NEW)
    assert env.updater.maybe_auto_check()["state"] == "available"


def test_auto_check_survives_restart_without_rechecking(env, tmp_path):
    env.set_check(True)
    env.github.publish(CURRENT)
    env.updater.maybe_auto_check()
    restarted = Updater(
        config_path=env.config_path, state_path=tmp_path / "update_state.json", current_version=CURRENT,
        api_url=env.github.api_url, download_prefix=env.github.download_prefix, clock=env.clock,
    )
    assert restarted.maybe_auto_check() is None
    assert len(env.github.hits) == 1


def test_new_version_is_notified_once(env):
    env.set_check(True)
    env.github.publish(NEW)
    env.updater.maybe_auto_check()
    assert [r["version"] for r in env.notified] == [NEW]
    env.clock.advance(CHECK_INTERVAL + 1)
    env.updater.maybe_auto_check()
    assert len(env.notified) == 1
    env.github.publish("0.3.0")
    env.clock.advance(CHECK_INTERVAL + 1)
    env.updater.maybe_auto_check()
    assert [r["version"] for r in env.notified] == [NEW, "0.3.0"]


def test_status_shows_available_only_when_auto_check_is_on(env):
    env.github.publish(NEW)
    env.updater.check()
    assert env.updater.status()["enabled"] is False
    assert env.updater.status()["available"] is None
    env.set_check(True)
    status = env.updater.status()
    assert status["enabled"] is True
    assert status["available"]["version"] == NEW
    assert status["current"] == CURRENT


def test_status_forgets_release_once_it_is_installed(env, tmp_path):
    env.set_check(True)
    env.github.publish(NEW)
    env.updater.maybe_auto_check()
    upgraded = Updater(
        config_path=env.config_path, state_path=tmp_path / "update_state.json", current_version=NEW,
        api_url=env.github.api_url, download_prefix=env.github.download_prefix,
    )
    assert upgraded.status()["available"] is None


def test_install_downloads_verifies_and_launches_installer(env, tmp_path):
    env.github.publish(NEW)
    env.updater.install_sync()
    assert len(env.launched) == 1
    path = env.launched[0]
    assert path.parent == tmp_path / "updates"
    assert path.read_bytes() == INSTALLER_BYTES
    assert env.quit_calls == 1
    assert env.updater.status()["install"]["state"] == "launched"


def test_install_works_while_auto_check_is_off(env):
    env.github.publish(NEW)
    env.updater.install_sync()
    assert len(env.launched) == 1


def test_checksum_mismatch_is_refused(env, tmp_path):
    env.github.publish(NEW, checksum="0" * 64)
    env.updater.install_sync()
    assert env.launched == []
    assert env.quit_calls == 0
    install = env.updater.status()["install"]
    assert install["state"] == "failed"
    assert "SHA-256" in install["error"]
    assert list((tmp_path / "updates").glob("*")) == []


def test_checksum_for_a_different_file_is_refused(env):
    env.github.publish(NEW)
    name = f"LumiaBriefingRoom-{NEW}-setup.exe"
    digest = hashlib.sha256(INSTALLER_BYTES).hexdigest()
    env.github.routes[f"/o/r/releases/download/v{NEW}/{name}.sha256"] = (200, f"{digest} *other.exe\n".encode())
    env.updater.install_sync()
    assert env.launched == []
    assert env.updater.status()["install"]["state"] == "failed"


def test_download_failure_leaves_no_partial_file(env, tmp_path):
    env.github.publish(NEW)
    del env.github.routes[f"/o/r/releases/download/v{NEW}/LumiaBriefingRoom-{NEW}-setup.exe"]
    env.updater.install_sync()
    assert env.launched == []
    assert env.updater.status()["install"]["state"] == "failed"
    assert list((tmp_path / "updates").glob("*")) == []


def test_install_when_already_latest_does_nothing(env):
    env.github.publish(CURRENT)
    env.updater.install_sync()
    assert env.launched == []
    assert env.updater.status()["install"]["state"] == "failed"


def test_launcher_failure_is_reported_and_app_keeps_running(env):
    env.github.publish(NEW)

    def broken(path):
        raise OSError("실행 거부")

    env.updater._launcher = broken
    env.updater.install_sync()
    assert env.quit_calls == 0
    assert env.updater.status()["install"]["state"] == "failed"


def test_old_installers_are_cleaned_before_download(env, tmp_path):
    stale = tmp_path / "updates" / "LumiaBriefingRoom-0.0.1-setup.exe"
    stale.parent.mkdir()
    stale.write_bytes(b"old")
    env.github.publish(NEW)
    env.updater.install_sync()
    assert not stale.exists()


def test_real_launcher_is_refused_outside_a_frozen_build(tmp_path, github):
    github.publish(NEW)
    env = Env(tmp_path, github)
    updater = Updater(
        config_path=env.config_path, state_path=tmp_path / "s.json", download_dir=tmp_path / "u",
        current_version=CURRENT, api_url=github.api_url, download_prefix=github.download_prefix, frozen=False,
    )
    updater.install_sync()
    assert updater.status()["install"]["state"] == "failed"
    assert "개발" in updater.status()["install"]["error"]


def test_start_install_runs_in_background_and_ignores_double_start(env):
    env.github.publish(NEW)
    assert env.updater.start_install() is True
    env.updater.wait_install(timeout=10)
    assert env.updater.status()["install"]["state"] == "launched"
    assert len(env.launched) == 1


def test_installer_command_is_silent_and_relaunches():
    command = installer_command("C:/x/setup.exe")
    assert command[0] == "C:/x/setup.exe"
    assert "/SILENT" in command
    assert "/RELAUNCH=1" in command


def test_installer_launch_breaks_away_from_the_kill_on_close_job():
    assert procs.installer_flags(platform="win32") & procs.CREATE_BREAKAWAY_FROM_JOB
    assert procs.JOB_OBJECT_LIMIT_BREAKAWAY_OK & procs.job_limit_flags()
    assert procs.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE & procs.job_limit_flags()
