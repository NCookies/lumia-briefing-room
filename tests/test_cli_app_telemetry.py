import threading

from lumia_briefing_room.cli import app as cli_app


class FakeSender:
    def __init__(self):
        self.started = threading.Event()
        self.stop = None

    def run_forever(self, stop):
        self.stop = stop
        self.started.set()


def test_start_telemetry_runs_the_sender_in_a_daemon_thread_that_can_be_stopped(tmp_path):
    sender = FakeSender()
    thread, stop = cli_app.start_telemetry(tmp_path / "config.json", sender=sender)
    assert sender.started.wait(2) and thread.daemon and sender.stop is stop
    assert not stop.is_set()


def test_start_telemetry_builds_a_sender_for_the_given_config_when_none_is_injected(tmp_path, monkeypatch):
    seen = {}

    class Recorded(FakeSender):
        def __init__(self, *, config_path):
            super().__init__()
            seen["config_path"] = config_path

    monkeypatch.setattr(cli_app, "TelemetrySender", Recorded)
    thread, _ = cli_app.start_telemetry(tmp_path / "config.json")
    thread.join(2)
    assert seen["config_path"] == tmp_path / "config.json"
