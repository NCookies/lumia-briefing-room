import time

from test_api_games import KEY, client  # noqa: F401  (같은 게임 픽스처를 쓴다)

from lumia_briefing_room.api import game_routes
from lumia_briefing_room.pipeline.reanalyze_game import REANALYZE_CANDIDATES, REANALYZE_FULL, ReanalyzeError


def wait_done(client, key=KEY, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        status = client.get(f"/api/games/{key}/reanalyze/status").json()
        if status["state"] not in ("running", "queued"):
            return status
        time.sleep(0.02)
    raise AssertionError("다시 분석이 끝나지 않았다")


def test_plan_reports_which_way_the_game_can_be_analyzed(client, monkeypatch):
    monkeypatch.setattr(game_routes, "reanalyze_mode", lambda *a, **k: REANALYZE_FULL)
    assert client.get(f"/api/games/{KEY}/reanalyze").json() == {"mode": "full"}
    monkeypatch.setattr(game_routes, "reanalyze_mode", lambda *a, **k: REANALYZE_CANDIDATES)
    assert client.get(f"/api/games/{KEY}/reanalyze").json() == {"mode": "candidates"}
    monkeypatch.setattr(game_routes, "reanalyze_mode", lambda *a, **k: None)
    assert client.get(f"/api/games/{KEY}/reanalyze").json() == {"mode": None}
    assert client.get("/api/games/20990101_000000/reanalyze").status_code == 404


def test_reanalyze_runs_in_the_background_and_reports_progress_and_the_mode(client, monkeypatch):
    calls = []

    def fake(**kw):
        calls.append(kw["key"])
        kw["on_progress"](0.5)
        return REANALYZE_CANDIDATES

    monkeypatch.setattr(game_routes, "reanalyze_game", fake)
    monkeypatch.setattr(game_routes, "reanalyze_mode", lambda *a, **k: REANALYZE_CANDIDATES)
    resp = client.post(f"/api/games/{KEY}/reanalyze")
    assert resp.status_code == 202
    status = wait_done(client)
    assert status["state"] == "done" and status["mode"] == "candidates" and status["fraction"] == 1.0
    assert resp.json()["mode"] == "candidates", "진행 문구가 방식을 알 수 있게 시작할 때 이미 알려 준다"
    assert calls == [KEY]


def test_a_failure_is_reported_with_the_user_facing_message(client, monkeypatch):
    def boom(**kw):
        raise ReanalyzeError("원본 녹화도 풀영상도 남아 있지 않아 다시 분석할 수 없습니다")

    monkeypatch.setattr(game_routes, "reanalyze_game", boom)
    monkeypatch.setattr(game_routes, "reanalyze_mode", lambda *a, **k: REANALYZE_FULL)
    client.post(f"/api/games/{KEY}/reanalyze")
    status = wait_done(client)
    assert status["state"] == "error" and "다시 분석할 수 없습니다" in status["message"]


def test_an_unexpected_error_does_not_leak_a_traceback(client, monkeypatch):
    def boom(**kw):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(game_routes, "reanalyze_game", boom)
    monkeypatch.setattr(game_routes, "reanalyze_mode", lambda *a, **k: REANALYZE_FULL)
    client.post(f"/api/games/{KEY}/reanalyze")
    status = wait_done(client)
    assert status["state"] == "error" and status["message"].startswith("다시 분석에 실패했습니다")


def test_the_same_game_pressed_twice_runs_once_and_can_be_requested_again_afterwards(client, monkeypatch):
    import threading

    release = threading.Event()
    calls = []
    monkeypatch.setattr(game_routes, "reanalyze_mode", lambda *a, **k: REANALYZE_FULL)
    monkeypatch.setattr(game_routes, "reanalyze_game", lambda **kw: (calls.append(kw["key"]), release.wait(2), REANALYZE_FULL)[2])
    assert client.post(f"/api/games/{KEY}/reanalyze").status_code == 202
    assert client.post(f"/api/games/{KEY}/reanalyze").status_code == 202, "실행 중인 같은 게임을 또 눌러도 거부하지 않는다"
    release.set()
    wait_done(client)
    assert client.post(f"/api/games/{KEY}/reanalyze").status_code == 202
    wait_done(client)
    assert calls == [KEY, KEY]


def test_reanalyze_is_refused_up_front_when_neither_the_recording_nor_the_full_video_is_left(client, monkeypatch):
    monkeypatch.setattr(game_routes, "reanalyze_mode", lambda *a, **k: None)
    resp = client.post(f"/api/games/{KEY}/reanalyze")
    assert resp.status_code == 409 and "다시 분석할 수 없습니다" in resp.json()["detail"]
    assert client.get(f"/api/games/{KEY}/reanalyze/status").json()["state"] == "idle", "줄에 넣지 않는다"


def test_status_is_idle_before_any_run_and_unknown_games_are_404(client):
    assert client.get(f"/api/games/{KEY}/reanalyze/status").json()["state"] == "idle"
    assert client.get("/api/games/20990101_000000/reanalyze/status").status_code == 404
    assert client.post("/api/games/20990101_000000/reanalyze").status_code == 404


def test_a_full_video_request_waits_behind_a_running_reanalyze_and_can_be_cancelled(client, monkeypatch):
    import threading
    from pathlib import Path

    release = threading.Event()
    monkeypatch.setattr(game_routes, "reanalyze_mode", lambda *a, **k: REANALYZE_FULL)
    monkeypatch.setattr(game_routes, "reanalyze_game", lambda **kw: (release.wait(2), REANALYZE_FULL)[1])
    monkeypatch.setattr(game_routes, "can_rebuild", lambda *a, **k: True)
    monkeypatch.setattr(game_routes, "discover_ffmpeg", lambda: Path("ffmpeg"))
    ran = []
    monkeypatch.setattr(game_routes, "rebuild_full_video", lambda **kw: ran.append(kw["key"]))
    assert client.post(f"/api/games/{KEY}/reanalyze").status_code == 202

    queued = client.post(f"/api/games/{KEY}/full-video")
    assert queued.status_code == 202 and queued.json()["state"] == "queued" and queued.json()["position"] == 1
    assert client.get(f"/api/games/{KEY}/full-video/status").json()["position"] == 1

    assert client.delete(f"/api/games/{KEY}/queue").status_code == 200
    assert client.get(f"/api/games/{KEY}/full-video/status").json()["state"] == "idle"
    assert client.delete(f"/api/games/{KEY}/queue").status_code == 409, "취소할 대기 요청이 없다"
    release.set()
    wait_done(client)
    assert ran == [], "취소한 요청은 돌지 않는다"


def test_queued_work_does_not_start_while_the_live_watcher_is_processing_a_game(client, monkeypatch):
    """감시가 게임을 처리하는 동안(링버퍼가 원본을 지우기 전에 끝내야 한다)에는 대기열이 새 분석을 시작하지 않는다."""
    from lumia_briefing_room import activity

    monkeypatch.setattr(game_routes, "reanalyze_mode", lambda *a, **k: REANALYZE_FULL)
    ran = []
    monkeypatch.setattr(game_routes, "reanalyze_game", lambda **kw: (ran.append(1), REANALYZE_FULL)[1])
    with activity.registry.track("watch", "감시가 게임 처리 중"):
        assert client.post(f"/api/games/{KEY}/reanalyze").json()["state"] == "queued"
        time.sleep(0.3)
        assert ran == [] and client.get(f"/api/games/{KEY}/reanalyze/status").json()["position"] == 1
    wait_done(client, timeout=5)
    assert ran == [1]
