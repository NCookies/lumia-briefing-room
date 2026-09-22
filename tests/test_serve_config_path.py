from lumia_briefing_room.cli import serve
from lumia_briefing_room.config import DEFAULT_CONFIG_PATH, Config


def run_main(monkeypatch, argv):
    seen = {}

    def fake_build_app(cfg, *, config_path=None):
        seen["config_path"] = config_path
        return object()

    class FakeServer:
        should_exit = False

    class FakeThread:
        def join(self, timeout=None):
            pass

    monkeypatch.setattr(serve, "load_config", lambda path=None: Config())
    monkeypatch.setattr(serve, "build_app", fake_build_app)
    monkeypatch.setattr(serve, "run_server_in_thread", lambda app, host, port: (FakeServer(), FakeThread()))
    monkeypatch.setattr(serve, "wait_until_started", lambda server: True)
    monkeypatch.setattr(serve, "open_ui", lambda url: None)
    serve.main(argv)
    return seen["config_path"]


def test_serve_without_config_flag_saves_settings_to_the_default_file(monkeypatch):
    assert run_main(monkeypatch, []) == DEFAULT_CONFIG_PATH


def test_serve_with_config_flag_uses_that_file(monkeypatch, tmp_path):
    path = tmp_path / "mine.json"

    assert run_main(monkeypatch, ["--config", str(path)]) == path
