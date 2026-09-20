from lumia_briefing_room.cli.app import make_on_open, resolve_port


def test_resolve_port_auto_picks_a_free_port():
    port = resolve_port("auto")
    assert isinstance(port, int)
    assert 1 <= port <= 65535


def test_resolve_port_fixed_value_is_used_as_is():
    assert resolve_port(8123) == 8123
    assert resolve_port("8123") == 8123


def test_make_on_open_starts_server_once_and_opens_browser(monkeypatch):
    started = []
    opened = []

    def fake_build_app(cfg, *, config_path=None):
        return "the-app"

    def fake_run_server_in_thread(app, *, host, port):
        started.append((app, host, port))
        return "server", "thread"

    def fake_wait_until_started(server, **kwargs):
        return True

    monkeypatch.setattr("lumia_briefing_room.cli.app.serve_cli.build_app", fake_build_app)
    monkeypatch.setattr(
        "lumia_briefing_room.cli.app.serve_cli.run_server_in_thread", fake_run_server_in_thread
    )
    monkeypatch.setattr(
        "lumia_briefing_room.cli.app.serve_cli.wait_until_started", fake_wait_until_started
    )
    monkeypatch.setattr("lumia_briefing_room.cli.app.load_config", lambda path: "the-cfg")

    on_open = make_on_open(host="127.0.0.1", port=8123, open_browser=opened.append)

    on_open()
    on_open()

    assert started == [("the-app", "127.0.0.1", 8123)]
    assert opened == ["http://127.0.0.1:8123/", "http://127.0.0.1:8123/"]


def test_watch_controller_toggle_starts_and_stops(monkeypatch):
    import threading
    import time

    started = threading.Event()
    calls = []

    def fake_run(args, *, should_stop=lambda: False):
        calls.append(args)
        started.set()
        while not should_stop():
            time.sleep(0.005)

    monkeypatch.setattr("lumia_briefing_room.cli.app.run", fake_run)

    from lumia_briefing_room.cli.app import make_watch_controller

    on_toggle_watch, watch_enabled = make_watch_controller("fake-args", auto_start=False)
    assert watch_enabled() is False

    on_toggle_watch()  # 시작
    assert started.wait(timeout=1.0)
    assert watch_enabled() is True
    assert calls == ["fake-args"]

    on_toggle_watch()  # 정지
    assert watch_enabled() is False


def test_watch_controller_auto_start_runs_immediately(monkeypatch):
    import threading

    started = threading.Event()

    def fake_run(args, *, should_stop=lambda: False):
        started.set()
        while not should_stop():
            threading.Event().wait(0.005)

    monkeypatch.setattr("lumia_briefing_room.cli.app.run", fake_run)

    from lumia_briefing_room.cli.app import make_watch_controller

    _on_toggle_watch, watch_enabled = make_watch_controller("fake-args", auto_start=True)
    assert started.wait(timeout=1.0)
    assert watch_enabled() is True


def test_should_open_ui_on_start_follows_flag_and_start_minimized():
    from lumia_briefing_room.cli.app import should_open_ui_on_start
    from lumia_briefing_room.config import Config, UiConfig

    minimized = Config(ui=UiConfig(start_minimized=True))
    visible = Config(ui=UiConfig(start_minimized=False))

    assert should_open_ui_on_start(minimized, open_ui=False) is False
    assert should_open_ui_on_start(minimized, open_ui=True) is True
    assert should_open_ui_on_start(visible, open_ui=False) is True
