import threading

from lumia_briefing_room.cli import app as cli_app


class FakeUpdater:
    def __init__(self):
        self.started = threading.Event()
        self.stop = None

    def run_forever(self, stop):
        self.stop = stop
        self.started.set()


def test_start_update_checks_runs_the_updater_in_a_daemon_thread_that_can_be_stopped(tmp_path):
    updater = FakeUpdater()
    thread, stop = cli_app.start_update_checks(tmp_path / "config.json", notify=lambda r: None, updater=updater)
    assert updater.started.wait(2) and thread.daemon and updater.stop is stop
    assert not stop.is_set()


def test_update_notice_names_the_version_and_where_to_update():
    message, title = cli_app.update_notice({"version": "0.2.0"})
    assert "0.2.0" in message and "정보·진단" in message
    assert title == "루미아 브리핑룸"


def test_quit_after_update_launch_waits_before_quitting():
    scheduled = []

    class FakeTimer:
        def __init__(self, delay, fn):
            scheduled.append((delay, fn))

        def start(self):
            pass

    quits = []
    cli_app.quit_after_update_launch(lambda: quits.append(1), delay=2.5, timer=FakeTimer)()
    assert quits == [] and scheduled[0][0] == 2.5
    scheduled[0][1]()
    assert quits == [1]


def test_make_on_open_hands_the_update_quit_hook_to_the_server_app(monkeypatch):
    class FakeApp:
        class state:
            pass

    fake = FakeApp()
    monkeypatch.setattr("lumia_briefing_room.cli.app.serve_cli.build_app", lambda cfg, *, config_path=None: fake)
    monkeypatch.setattr(
        "lumia_briefing_room.cli.app.serve_cli.run_server_in_thread", lambda app, *, host, port: ("s", "t")
    )
    monkeypatch.setattr("lumia_briefing_room.cli.app.serve_cli.wait_until_started", lambda server, **kw: True)
    monkeypatch.setattr("lumia_briefing_room.cli.app.load_config", lambda path: "cfg")

    hook = lambda: None  # noqa: E731
    cli_app.make_on_open(port=1, open_browser=lambda url: None, on_update_launched=hook)()
    assert fake.state.on_update_launched is hook


def _stub_server(monkeypatch):
    started = []

    class FakeApp:
        class state:
            pass

    monkeypatch.setattr("lumia_briefing_room.cli.app.serve_cli.build_app", lambda cfg, *, config_path=None: FakeApp())
    monkeypatch.setattr(
        "lumia_briefing_room.cli.app.serve_cli.run_server_in_thread",
        lambda app, *, host, port: (started.append(port), ("server", "thread"))[1],
    )
    monkeypatch.setattr("lumia_briefing_room.cli.app.serve_cli.wait_until_started", lambda server, **kw: True)
    monkeypatch.setattr("lumia_briefing_room.cli.app.load_config", lambda path: "cfg")
    return started


def test_ensure_server_starts_the_server_without_opening_a_browser(monkeypatch):
    started = _stub_server(monkeypatch)
    opened = []
    on_open = cli_app.make_on_open(port=7, open_browser=opened.append)

    on_open.ensure_server()

    assert started == [7] and opened == []


def test_opening_after_ensure_server_reuses_the_running_server(monkeypatch):
    started = _stub_server(monkeypatch)
    opened = []
    on_open = cli_app.make_on_open(port=7, open_browser=opened.append)

    on_open.ensure_server()
    on_open()
    on_open()

    assert started == [7]
    assert len(opened) == 2


def test_the_app_accepts_a_start_server_flag_for_the_installer_relaunch():
    args = cli_app.build_app_parser().parse_args(["--start-server"])
    assert args.start_server is True


def test_the_installer_relaunches_the_app_with_its_server_started():
    from pathlib import Path

    iss = (Path(__file__).resolve().parents[1] / "installer" / "lumia.iss").read_text(encoding="utf-8")
    relaunch = [line for line in iss.splitlines() if "Check: RelaunchRequested" in line]
    assert len(relaunch) == 1 and '--start-server' in relaunch[0]


def test_installer_launch_is_deferred_until_the_app_has_exited():
    launched = []
    deferred = cli_app.DeferredInstaller(launch=launched.append)

    deferred.launcher("C:/x/setup.exe")

    assert launched == []
    deferred.run_pending()
    assert launched == ["C:/x/setup.exe"]
    deferred.run_pending()
    assert launched == ["C:/x/setup.exe"]


def test_run_pending_without_an_installer_does_nothing():
    launched = []
    cli_app.DeferredInstaller(launch=launched.append).run_pending()
    assert launched == []


def test_a_failing_deferred_launch_does_not_crash_the_shutdown(caplog):
    def broken(path):
        raise OSError("실행 거부")

    deferred = cli_app.DeferredInstaller(launch=broken)
    deferred.launcher("C:/x/setup.exe")
    deferred.run_pending()
    assert "설치기" in caplog.text


def test_update_route_hands_the_deferred_launcher_to_the_updater(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from lumia_briefing_room.api import update_routes
    from lumia_briefing_room.api.app import create_app
    from lumia_briefing_room.config import Config

    captured = {}

    class FakeUpdater:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def status(self):
            return {"enabled": False, "current": "0", "lastChecked": None, "available": None, "install": {}}

    monkeypatch.setattr(update_routes, "Updater", FakeUpdater)
    app = create_app(Config(), config_path=tmp_path / "c.json")
    marker = object()
    app.state.update_launcher = marker
    TestClient(app).get("/api/update/status")
    assert captured["launcher"] is marker
