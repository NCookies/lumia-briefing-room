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


def test_the_silent_installer_pins_its_progress_window_on_top_of_the_browser():
    from pathlib import Path

    iss = (Path(__file__).resolve().parents[1] / "installer" / "lumia.iss").read_text(encoding="utf-8-sig")
    assert "SetWindowPos@user32.dll" in iss
    assert "WizardSilent" in iss
    assert "GetActiveWindow" in iss


def test_a_browser_is_opened_after_an_update_when_no_page_came_back():
    opened, sleeps = [], []

    class FakeOpen:
        ensure_calls = 0

        def __call__(self):
            opened.append(1)

        def ensure_server(self):
            self.ensure_calls += 1

        def client_hits(self):
            return 0

    on_open = FakeOpen()
    cli_app.open_after_update(on_open, wait_sec=2.0, poll_sec=0.5, sleep=sleeps.append)
    assert opened == [1] and on_open.ensure_calls == 1
    assert sum(sleeps) >= 2.0


def test_no_second_window_when_the_old_tab_reloaded_itself():
    opened = []

    class FakeOpen:
        hits = [0, 0, 3]

        def __call__(self):
            opened.append(1)

        def ensure_server(self):
            pass

        def client_hits(self):
            return self.hits.pop(0) if self.hits else 3

    cli_app.open_after_update(FakeOpen(), wait_sec=5.0, poll_sec=0.5, sleep=lambda s: None)
    assert opened == []


def test_first_run_notice_tells_where_the_app_lives_and_what_happens_next():
    message, title = cli_app.first_run_notice()
    assert title == "루미아 브리핑룸"
    assert "브라우저" in message and "아이콘" in message


def test_announce_first_run_notifies_only_while_the_first_run_screen_is_still_needed(tmp_path):
    from lumia_briefing_room.config import Config
    from lumia_briefing_room.consent import CONSENT_VERSION

    shown = []
    fresh = Config()
    assert cli_app.announce_first_run(fresh, lambda message, title: shown.append((message, title))) is True
    assert len(shown) == 1

    answered = Config()
    answered.consent.version = CONSENT_VERSION
    assert cli_app.announce_first_run(answered, lambda message, title: shown.append((message, title))) is False
    assert len(shown) == 1
    assert cli_app.announce_first_run(answered, lambda message, title: shown.append((message, title)), open_ui=True) is True
    assert len(shown) == 2


def test_announce_first_run_survives_a_failing_notification():
    from lumia_briefing_room.config import Config

    def boom(message, title):
        raise RuntimeError("no tray")

    assert cli_app.announce_first_run(Config(), boom) is True
