from lumia_briefing_room.cli.app import access_url, make_on_open, port_candidates, resolve_port


def test_resolve_port_auto_picks_a_free_port():
    port = resolve_port("auto")
    assert isinstance(port, int)
    assert 1 <= port <= 65535


def test_port_candidates_try_80_then_configured_port_then_next_20():
    assert port_candidates(8765) == [80, *range(8765, 8786)]
    assert port_candidates("8765") == port_candidates(8765)


def test_port_candidates_do_not_repeat_80_and_auto_is_the_default():
    assert port_candidates(80) == list(range(80, 101))
    assert port_candidates("auto") == port_candidates(8765)


def test_resolve_port_auto_is_not_random_when_80_is_free():
    assert resolve_port("auto", is_free=lambda p: True) == 80
    assert resolve_port("auto", is_free=lambda p: p != 80) == 8765


def test_resolve_port_prefers_80_when_free():
    assert resolve_port(8765, is_free=lambda p: True) == 80


def test_resolve_port_falls_back_to_configured_port_when_80_is_busy():
    assert resolve_port(8765, is_free=lambda p: p != 80) == 8765
    assert resolve_port("8765", is_free=lambda p: p != 80) == 8765


def test_resolve_port_falls_back_to_next_free_port_when_busy():
    assert resolve_port(8765, is_free=lambda p: p not in (80, 8765, 8766)) == 8767


def test_resolve_port_uses_any_free_port_when_all_candidates_are_busy():
    port = resolve_port(8765, is_free=lambda p: False)
    assert 1 <= port <= 65535


def test_access_url_drops_port_80_and_keeps_others():
    assert access_url(80) == "http://lumia-briefingroom.localhost/"
    assert access_url(8765) == "http://lumia-briefingroom.localhost:8765/"


def test_default_ui_port_is_fixed():
    from lumia_briefing_room.config import UiConfig

    assert UiConfig().port == 8765


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
    assert opened == ["http://lumia-briefingroom.localhost:8123/"] * 2


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
    from lumia_briefing_room.config import Config, ConsentConfig, UiConfig
    from lumia_briefing_room.consent import CONSENT_VERSION

    answered = ConsentConfig(version=CONSENT_VERSION)
    minimized = Config(ui=UiConfig(start_minimized=True), consent=answered)
    visible = Config(ui=UiConfig(start_minimized=False), consent=answered)

    assert should_open_ui_on_start(minimized, open_ui=False) is False
    assert should_open_ui_on_start(minimized, open_ui=True) is True
    assert should_open_ui_on_start(visible, open_ui=False) is True


def test_first_run_opens_ui_even_when_start_minimized():
    from lumia_briefing_room.cli.app import should_open_ui_on_start
    from lumia_briefing_room.config import Config, ConsentConfig, UiConfig
    from lumia_briefing_room.consent import CONSENT_VERSION

    fresh = Config(ui=UiConfig(start_minimized=True))
    answered = Config(ui=UiConfig(start_minimized=True), consent=ConsentConfig(version=CONSENT_VERSION))

    assert should_open_ui_on_start(fresh, open_ui=False) is True
    assert should_open_ui_on_start(answered, open_ui=False) is False


def test_watch_waits_and_retries_until_start_conditions_are_met():
    import threading

    from lumia_briefing_room.cli.app import _run_watch_safely

    attempts = []

    def flaky_run(args, should_stop):
        attempts.append(1)
        if len(attempts) < 3:
            raise SystemExit("녹화 폴더를 찾을 수 없다")

    _run_watch_safely(None, threading.Event(), run_fn=flaky_run, retry_sec=0)
    assert len(attempts) == 3


def test_watch_retry_stops_when_asked():
    import threading

    from lumia_briefing_room.cli.app import _run_watch_safely

    stop = threading.Event()
    attempts = []

    def failing_run(args, should_stop):
        attempts.append(1)
        stop.set()
        raise SystemExit("ffmpeg")

    _run_watch_safely(None, stop, run_fn=failing_run, retry_sec=0)
    assert len(attempts) == 1


def test_watch_does_not_retry_unexpected_exceptions():
    import threading

    from lumia_briefing_room.cli.app import _run_watch_safely

    attempts = []

    def broken_run(args, should_stop):
        attempts.append(1)
        raise RuntimeError("boom")

    _run_watch_safely(None, threading.Event(), run_fn=broken_run, retry_sec=0)
    assert len(attempts) == 1


def test_watch_restart_reruns_with_fresh_settings_while_running(monkeypatch):
    """녹화 폴더를 바꾸면 감시가 시작 때 읽은 옛 폴더를 계속 쓰지 않게 다시 시작한다."""
    import threading
    import time

    starts = []
    stops = []

    def fake_run(args, *, should_stop=lambda: False):
        index = len(starts)
        starts.append(index)
        while not should_stop():
            time.sleep(0.005)
        stops.append(index)

    monkeypatch.setattr("lumia_briefing_room.cli.app.run", fake_run)
    from lumia_briefing_room.cli.app import make_watch_controller

    on_toggle_watch, watch_enabled = make_watch_controller("fake-args", auto_start=True)
    deadline = time.time() + 2
    while not starts and time.time() < deadline:
        time.sleep(0.005)

    on_toggle_watch.restart()

    deadline = time.time() + 3
    while len(starts) < 2 and time.time() < deadline:
        time.sleep(0.005)
    assert starts == [0, 1]
    assert stops == [0]
    assert watch_enabled() is True
    on_toggle_watch()


def test_watch_restart_does_not_resume_a_watch_the_user_paused(monkeypatch):
    import time

    starts = []

    def fake_run(args, *, should_stop=lambda: False):
        starts.append(1)
        while not should_stop():
            time.sleep(0.005)

    monkeypatch.setattr("lumia_briefing_room.cli.app.run", fake_run)
    from lumia_briefing_room.cli.app import make_watch_controller

    on_toggle_watch, watch_enabled = make_watch_controller("fake-args", auto_start=False)

    on_toggle_watch.restart()

    time.sleep(0.1)
    assert starts == []
    assert watch_enabled() is False


def test_make_on_open_connects_the_watch_restart_to_the_server_app(monkeypatch):
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
    from lumia_briefing_room.cli.app import make_on_open

    restart = lambda: None  # noqa: E731
    make_on_open(port=1, open_browser=lambda url: None, on_recording_root_changed=restart)()

    assert fake.state.on_recording_root_changed is restart
