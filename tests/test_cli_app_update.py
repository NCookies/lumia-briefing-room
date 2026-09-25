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
