import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api import backfill_routes as routes
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig
from lumia_briefing_room.pipeline.backfill import BackfillProgress, BackfillResult


class FakeRun:
    """run_backfill 대신 돌아, 진행을 알리고 취소 신호를 존중한다."""

    def __init__(self):
        self.calls = []
        self.release = threading.Event()
        self.started = threading.Event()
        self.result = BackfillResult(sessions_scanned=2, games_found=5, games_processed=3, clips_created=20)

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        on_progress = kwargs["on_progress"]
        cancel = kwargs["cancel"]
        on_progress(BackfillProgress("scan", 0.25, "10분 지점", session_index=1, session_total=2))
        self.started.set()
        while not self.release.wait(0.01):
            if cancel.is_set():
                self.result.cancelled = True
                return self.result
        on_progress(BackfillProgress("done", 1.0, "", games_done=3, games_total=3, clips=20))
        return self.result


@pytest.fixture
def env(tmp_path, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(routes, "run_backfill", fake)
    monkeypatch.setattr(routes, "discover_ffmpeg", lambda: Path("ffmpeg"))
    monkeypatch.setattr(routes, "resolve_recording_root", lambda configured: tmp_path / "video")
    monkeypatch.setattr(routes, "collect_log_starts", lambda cfg: [datetime(2026, 9, 24, 6, 6, tzinfo=timezone.utc)])
    monkeypatch.setattr(routes, "SteamSessionScanner", lambda *a, **k: "scanner")
    monkeypatch.setattr(routes, "make_process_window", lambda *a, **k: "process")
    (tmp_path / "video").mkdir()
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp"))
    client = TestClient(create_app(cfg, config_path=tmp_path / "c.json"))
    return client, fake, tmp_path


def _wait_state(client, wanted, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get("/api/backfill").json()
        if body["state"] in wanted:
            return body
        time.sleep(0.02)
    raise AssertionError(f"{wanted} 상태가 안 됐다: {body}")


def test_idle_before_anything_runs(env):
    client, _, _ = env
    assert client.get("/api/backfill").json()["state"] == "idle"


def test_start_runs_in_the_background_and_reports_progress(env):
    client, fake, _ = env

    resp = client.post("/api/backfill/start")
    assert resp.status_code == 202
    assert fake.started.wait(2)

    body = client.get("/api/backfill").json()
    assert body["state"] == "running"
    assert body["phase"] == "scan" and body["fraction"] == pytest.approx(0.25)
    assert body["sessionIndex"] == 1 and body["sessionTotal"] == 2

    fake.release.set()
    done = _wait_state(client, {"done"})
    assert done["fraction"] == 1.0
    assert done["result"]["gamesProcessed"] == 3 and done["result"]["clipsCreated"] == 20


def test_start_passes_the_right_folders_and_the_known_games(env):
    client, fake, tmp = env
    client.post("/api/backfill/start")
    fake.started.wait(2)
    fake.release.set()
    _wait_state(client, {"done"})

    call = fake.calls[0]
    assert call["clips_dir"] == tmp / "clips"
    assert call["staging_root"].parent == call["state_dir"].parent
    assert datetime(2026, 9, 24, 6, 6, tzinfo=timezone.utc) in call["known_starts"], "로그로 아는 경기도 제외 대상이다"
    assert call["scanner"] == "scanner" and call["process_window"] == "process"


def test_a_second_start_while_running_is_refused(env):
    client, fake, _ = env
    client.post("/api/backfill/start")
    fake.started.wait(2)

    assert client.post("/api/backfill/start").status_code == 409

    fake.release.set()
    _wait_state(client, {"done"})


def test_cancel_stops_the_run_and_reports_cancelled(env):
    client, fake, _ = env
    client.post("/api/backfill/start")
    fake.started.wait(2)

    resp = client.post("/api/backfill/cancel")

    assert resp.status_code == 200
    body = _wait_state(client, {"cancelled"})
    assert body["result"]["cancelled"] is True


def test_cancel_when_nothing_runs_is_harmless(env):
    client, _, _ = env
    assert client.post("/api/backfill/cancel").status_code == 200
    assert client.get("/api/backfill").json()["state"] == "idle"


def test_can_start_again_after_it_finished(env):
    client, fake, _ = env
    client.post("/api/backfill/start")
    fake.started.wait(2)
    fake.release.set()
    _wait_state(client, {"done"})
    fake.started.clear()

    assert client.post("/api/backfill/start").status_code == 202
    _wait_state(client, {"done", "running"})


def test_a_crash_in_the_run_is_reported_as_an_error(env, monkeypatch):
    client, _, _ = env

    def boom(**kwargs):
        raise RuntimeError("디스크 오류")

    monkeypatch.setattr(routes, "run_backfill", boom)
    client.post("/api/backfill/start")

    body = _wait_state(client, {"error"})
    assert "디스크 오류" in body["error"]
    assert client.post("/api/backfill/start").status_code == 202


def test_start_without_ffmpeg_is_503(env, monkeypatch):
    client, _, _ = env
    monkeypatch.setattr(routes, "discover_ffmpeg", lambda: None)
    assert client.post("/api/backfill/start").status_code == 503


def test_start_without_a_recording_folder_is_503(env, monkeypatch):
    client, _, _ = env
    monkeypatch.setattr(routes, "resolve_recording_root", lambda configured: None)
    assert client.post("/api/backfill/start").status_code == 503


def test_preview_reports_sessions_size_and_an_estimate(env, monkeypatch):
    client, _, tmp = env
    monkeypatch.setattr(
        routes, "estimate_backfill",
        lambda root, state_dir: {"sessions": 2, "segments": 3000, "videoSeconds": 9000.0, "sizeBytes": 8_000_000_000,
                                 "unscannedSeconds": 6000.0, "estimatedSeconds": 240.0},
    )

    body = client.get("/api/backfill/preview").json()

    assert body["sessions"] == 2 and body["estimatedSeconds"] == 240.0
    assert body["canStart"] is True
    assert body["recordingRoot"] == str(tmp / "video")


def test_preview_says_why_it_cannot_start(env, monkeypatch):
    client, _, _ = env
    monkeypatch.setattr(routes, "resolve_recording_root", lambda configured: None)

    body = client.get("/api/backfill/preview").json()

    assert body["canStart"] is False and body["reason"]


def test_preview_says_nothing_to_do_when_there_are_no_sessions(env, monkeypatch):
    client, _, _ = env
    monkeypatch.setattr(
        routes, "estimate_backfill",
        lambda root, state_dir: {"sessions": 0, "segments": 0, "videoSeconds": 0.0, "sizeBytes": 0,
                                 "unscannedSeconds": 0.0, "estimatedSeconds": 0.0},
    )

    body = client.get("/api/backfill/preview").json()

    assert body["canStart"] is False and "녹화" in body["reason"]
