import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api import vods as vods_module
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig, load_config, resolve_paths
from lumia_briefing_room.pipeline.vod_analyze import VodCancelled, VodProgress
from lumia_briefing_room.pipeline.vod_store import save_index, vod_id
from lumia_briefing_room.video.vod import VideoInfo


def write_video(path: Path, content: bytes = b"video-bytes" * 100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def write_vod_clip(root: Path, vid: str, game: int, start: int, **meta):
    root.mkdir(parents=True, exist_ok=True)
    cid = f"vod_{vid}_g{game:02d}_{start:06d}"
    (root / f"{cid}.mp4").write_bytes(b"x" * 100)
    data = {"title": cid, "source": "vod", "vodId": vid, "vodGameIndex": game, "tags": ["kill"],
            "pinned": False, "deletedAt": None, "thumbnailPath": None, **meta}
    (root / f"{cid}.json").write_text(json.dumps(data), encoding="utf-8")
    return cid


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(vods_module, "discover_ffmpeg", lambda: tmp_path / "ffmpeg.exe")
    monkeypatch.setattr(vods_module, "_probe_info", lambda path, ffmpeg: None)
    videos = tmp_path / "videos"
    a = write_video(videos / "a.mp4", b"A" * 3000)
    b = write_video(videos / "sub" / "b.mkv", b"B" * 4000)
    write_video(videos / "notes.txt", b"not a video")
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", vod_clips=tmp_path / "vod", temp=tmp_path / "tmp"))
    vod_dir = resolve_paths(cfg.paths).library_vod  # 영상 클립 정보(색인·json)는 앱 데이터 library 에 있다
    cfg.vod.sources = [str(videos)]
    config_path = tmp_path / "config.json"
    from lumia_briefing_room.config import save_config
    save_config(cfg, config_path)
    app = create_app(cfg, config_path=config_path)
    return TestClient(app), a, b, vod_dir, config_path, videos


def by_id(resp):
    return {v["id"]: v for v in resp.json()}


def test_empty_when_no_sources(tmp_path):
    cfg = Config(paths=PathsConfig(vod_clips=tmp_path / "vod"))
    client = TestClient(create_app(cfg, config_path=tmp_path / "c.json"))

    assert client.get("/api/vods").json() == []


def test_lists_video_files_from_a_folder_source_ignoring_other_files(env):
    client, a, b, *_ = env

    listed = by_id(client.get("/api/vods"))

    assert set(listed) == {vod_id(a)}
    entry = listed[vod_id(a)]
    assert entry["name"] == "a.mp4" and entry["exists"] is True
    assert entry["status"] == "new" and entry["sizeBytes"] == 3000
    assert entry["games"] == [] and entry["clipCount"] == 0


def test_recursive_flag_includes_subfolders_and_files_can_be_sources(env):
    client, a, b, vod_dir, config_path, videos = env
    client.put("/api/config", json={"vod": {"recursive": True}})

    assert set(by_id(client.get("/api/vods"))) == {vod_id(a), vod_id(b)}

    client.put("/api/config", json={"vod": {"recursive": False, "sources": [str(b)]}})
    assert set(by_id(client.get("/api/vods"))) == {vod_id(b)}


def test_analyzed_vod_reports_status_games_and_live_clip_counts(env):
    client, a, b, vod_dir, *_ = env
    vid = vod_id(a)
    write_vod_clip(vod_dir, vid, 1, 10)
    write_vod_clip(vod_dir, vid, 1, 90)
    write_vod_clip(vod_dir, vid, 2, 10)
    save_index(vod_dir, {
        "id": vid, "path": str(a), "status": "done", "durationSec": 1234.0, "width": 1920, "height": 1080,
        "streamer": "인덱스 이름", "analyzedSec": 1234.0,
        "games": [{"index": 1, "startSec": 5.0, "endSec": 600.0, "result": {"placement": 2}, "clipIds": []},
                  {"index": 2, "startSec": 700.0, "endSec": 900.0, "result": None, "clipIds": []}],
        "clips": [],
    })

    entry = by_id(client.get("/api/vods"))[vid]

    assert entry["status"] == "done" and entry["durationSec"] == 1234.0
    assert (entry["width"], entry["height"]) == (1920, 1080)
    assert len(entry["games"]) == 2 and entry["games"][0]["result"]["placement"] == 2
    assert entry["clipCount"] == 3 and entry["clipBytes"] == 300
    assert entry["streamer"] == "인덱스 이름"


def test_vod_game_result_image_serves_the_stored_thumbnail_by_index(env):
    client, a, _, vod_dir, *_ = env
    vid = vod_id(a)
    (vod_dir / ".thumbs").mkdir(parents=True)
    (vod_dir / ".thumbs" / f"{vid}_g01_result.jpg").write_bytes(b"\xff\xd8fake-jpeg")
    save_index(vod_dir, {
        "id": vid, "path": str(a), "status": "done",
        "games": [{"index": 1, "startSec": 0.0, "endSec": 10.0,
                   "result": {"placement": 1, "imagePath": ".thumbs/" + vid + "_g01_result.jpg"}, "clipIds": []}],
        "clips": [],
    })

    resp = client.get(f"/api/vods/{vid}/games/1/result-image")

    assert resp.status_code == 200 and resp.content == b"\xff\xd8fake-jpeg"


def test_vod_game_result_image_404s_without_an_image_or_game(env):
    client, a, _, vod_dir, *_ = env
    vid = vod_id(a)
    save_index(vod_dir, {
        "id": vid, "path": str(a), "status": "done",
        "games": [{"index": 1, "startSec": 0.0, "endSec": 10.0, "result": None, "clipIds": []}],
        "clips": [],
    })

    assert client.get(f"/api/vods/{vid}/games/1/result-image").status_code == 404
    assert client.get(f"/api/vods/{vid}/games/99/result-image").status_code == 404
    assert client.get(f"/api/vods/does-not-exist/games/1/result-image").status_code == 404


def test_interrupted_analysis_is_reported_when_no_job_is_running(env):
    client, a, _, vod_dir, *_ = env
    save_index(vod_dir, {"id": vod_id(a), "path": str(a), "status": "analyzing", "analyzedSec": 300.0,
                         "durationSec": 1000.0, "games": [], "clips": []})

    assert by_id(client.get("/api/vods"))[vod_id(a)]["status"] == "interrupted"


def test_known_vod_whose_file_disappeared_is_still_listed(env):
    client, a, _, vod_dir, *_ = env
    gone = tmp = vod_dir.parent / "elsewhere.mp4"
    save_index(vod_dir, {"id": "deadbeef0001", "path": str(gone), "status": "done", "games": [], "clips": []})

    entry = by_id(client.get("/api/vods"))["deadbeef0001"]

    assert entry["exists"] is False and entry["name"] == "elsewhere.mp4" and entry["status"] == "done"


def test_streamer_name_is_saved_in_the_config_and_shown(env):
    client, a, _, _, config_path, _ = env
    vid = vod_id(a)

    resp = client.patch(f"/api/vods/{vid}", json={"streamer": "○○○"})

    assert resp.status_code == 200
    assert load_config(config_path).vod.streamers[vid] == "○○○"
    assert by_id(client.get("/api/vods"))[vid]["streamer"] == "○○○"
    assert client.patch("/api/vods/nope", json={"streamer": "x"}).status_code == 404


def test_clearing_the_streamer_name_removes_it(env):
    client, a, *_ = env
    vid = vod_id(a)
    client.patch(f"/api/vods/{vid}", json={"streamer": "이름"})

    resp = client.patch(f"/api/vods/{vid}", json={"streamer": "  "})

    assert resp.json()["streamer"] is None
    assert by_id(client.get("/api/vods"))[vid]["streamer"] is None


def test_video_date_falls_back_to_file_mtime(env):
    client, a, *_ = env
    vid = vod_id(a)
    import os
    from datetime import datetime

    mtime = datetime(2026, 9, 27, 15, 0).timestamp()
    os.utime(a, (mtime, mtime))

    entry = by_id(client.get("/api/vods"))[vid]

    assert entry["videoDate"] == "2026-09-27"


def test_video_date_prefers_creation_time_from_probe(env, monkeypatch):
    client, a, *_ = env
    from lumia_briefing_room.pipeline.vod_dates import date_from_creation_time

    monkeypatch.setattr(
        vods_module, "_probe_info",
        lambda path, ffmpeg: VideoInfo(
            width=1, height=1, fps=1.0, duration_sec=10.0, codec="h264",
            creation_time="2026-09-20T03:00:00.000000Z",
        ),
    )

    deadline = time.time() + 3
    entry = by_id(client.get("/api/vods"))[vod_id(a)]
    while entry["probing"] and time.time() < deadline:
        time.sleep(0.02)
        entry = by_id(client.get("/api/vods"))[vod_id(a)]

    assert entry["videoDate"] == date_from_creation_time("2026-09-20T03:00:00.000000Z")


def test_video_date_prefers_creation_time_saved_in_index(env):
    client, a, _, vod_dir, *_ = env
    from lumia_briefing_room.pipeline.vod_dates import date_from_creation_time

    save_index(vod_dir, {
        "id": vod_id(a), "path": str(a), "status": "done", "durationSec": 10.0,
        "creationTime": "2026-09-20T03:00:00.000000Z", "games": [], "clips": [],
    })

    entry = by_id(client.get("/api/vods"))[vod_id(a)]

    assert entry["videoDate"] == date_from_creation_time("2026-09-20T03:00:00.000000Z")


def test_video_date_user_override_wins_over_probe_and_mtime(env):
    client, a, *_ = env
    vid = vod_id(a)

    resp = client.patch(f"/api/vods/{vid}", json={"date": "2026-01-01"})

    assert resp.status_code == 200 and resp.json()["date"] == "2026-01-01"
    assert by_id(client.get("/api/vods"))[vid]["videoDate"] == "2026-01-01"


def test_patch_date_rejects_invalid_format(env):
    client, a, *_ = env
    vid = vod_id(a)

    resp = client.patch(f"/api/vods/{vid}", json={"date": "2026/01/01"})

    assert resp.status_code == 400


def test_clearing_the_date_override_falls_back_to_automatic_date(env):
    client, a, *_ = env
    vid = vod_id(a)
    client.patch(f"/api/vods/{vid}", json={"date": "2026-01-01"})

    resp = client.patch(f"/api/vods/{vid}", json={"date": ""})

    assert resp.json()["date"] is None
    assert by_id(client.get("/api/vods"))[vid]["videoDate"] is not None


class FakeAnalyze:
    def __init__(self, *, fail: Exception | None = None):
        self.release = threading.Event()
        self.started = threading.Event()
        self.calls = []
        self.fail = fail

    def __call__(self, path, cfg, **kw):
        self.calls.append((Path(path).name, kw.get("force"), kw.get("rebuild")))
        self.started.set()
        kw["on_progress"](VodProgress("decode", 0.4, 1, 2, "절반 가까이"))
        while not self.release.is_set():
            if kw["cancel"].is_set():
                raise VodCancelled()
            time.sleep(0.01)
        if self.fail:
            raise self.fail
        return {"status": "done", "games": [], "clips": []}


def wait_for(client, vid, state, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/vods/{vid}/analyze").json()
        if job["state"] == state:
            return job
        time.sleep(0.02)
    raise AssertionError(f"{state} 가 되지 않았다: {job}")


def test_analyze_runs_in_the_background_and_reports_progress(env, monkeypatch):
    client, a, *_ = env
    fake = FakeAnalyze()
    monkeypatch.setattr(vods_module, "analyze_vod", fake)
    vid = vod_id(a)

    assert client.post(f"/api/vods/{vid}/analyze", json={}).status_code == 202
    assert fake.started.wait(2)
    job = wait_for(client, vid, "running")

    assert job["phase"] == "decode" and job["fraction"] == 0.4
    assert job["games"] == 1 and job["clips"] == 2 and job["message"] == "절반 가까이"
    assert by_id(client.get("/api/vods"))[vid]["status"] == "analyzing"

    fake.release.set()
    wait_for(client, vid, "done")
    assert fake.calls == [("a.mp4", False, False)]


def test_a_second_analysis_waits_in_the_queue_instead_of_being_rejected(env, monkeypatch):
    client, a, b, *_ = env
    client.put("/api/config", json={"vod": {"recursive": True}})
    fake = FakeAnalyze()
    monkeypatch.setattr(vods_module, "analyze_vod", fake)
    va, vb = vod_id(a), vod_id(b)
    assert client.post(f"/api/vods/{va}/analyze", json={}).status_code == 202
    assert fake.started.wait(2)

    assert client.post(f"/api/vods/{vb}/analyze", json={}).status_code == 202
    entry = by_id(client.get("/api/vods"))[vb]
    assert entry["status"] == "queued" and entry["queuePosition"] == 1
    assert by_id(client.get("/api/vods"))[va]["queuePosition"] is None
    waiting = client.get(f"/api/vods/{vb}/analyze").json()
    assert waiting["state"] == "queued" and waiting["position"] == 1
    assert client.post(f"/api/vods/{vb}/analyze", json={"rebuild": True}).status_code == 202, "같은 영상을 또 눌러도 한 번만 줄 선다"
    assert client.get(f"/api/vods/{vb}/analyze").json()["position"] == 1
    assert client.post(f"/api/vods/{va}/analyze", json={}).status_code == 202, "실행 중인 영상을 또 눌러도 거부하지 않는다"
    assert client.post("/api/vods/nope/analyze", json={}).status_code == 404

    fake.release.set()
    wait_for(client, va, "done")
    wait_for(client, vb, "done")
    assert fake.calls == [("a.mp4", False, False), ("b.mkv", False, True)], "나중 요청(다시 만들기)이 대기 중이던 요청을 대체했다"


def test_cancelling_a_waiting_analysis_removes_it_from_the_queue(env, monkeypatch):
    client, a, b, *_ = env
    client.put("/api/config", json={"vod": {"recursive": True}})
    fake = FakeAnalyze()
    monkeypatch.setattr(vods_module, "analyze_vod", fake)
    va, vb = vod_id(a), vod_id(b)
    client.post(f"/api/vods/{va}/analyze", json={})
    assert fake.started.wait(2)
    client.post(f"/api/vods/{vb}/analyze", json={})

    assert client.delete(f"/api/vods/{vb}").status_code == 409, "대기 중인 영상은 지울 수 없다"
    assert client.post(f"/api/vods/{vb}/analyze/cancel").status_code == 200
    assert client.get(f"/api/vods/{vb}/analyze").json()["state"] == "cancelled"
    assert by_id(client.get("/api/vods"))[vb]["status"] == "new"
    assert client.post(f"/api/vods/{vb}/analyze/cancel").status_code == 409

    fake.release.set()
    wait_for(client, va, "done")
    assert fake.calls == [("a.mp4", False, False)], "취소한 영상은 돌지 않는다"


def test_cancel_stops_the_running_analysis(env, monkeypatch):
    client, a, *_ = env
    fake = FakeAnalyze()
    monkeypatch.setattr(vods_module, "analyze_vod", fake)
    vid = vod_id(a)
    client.post(f"/api/vods/{vid}/analyze", json={})
    assert fake.started.wait(2)

    assert client.post(f"/api/vods/{vid}/analyze/cancel").status_code == 200
    wait_for(client, vid, "cancelled")

    assert client.post(f"/api/vods/{vid}/analyze/cancel").status_code == 409


def test_analysis_errors_are_reported(env, monkeypatch):
    client, a, *_ = env
    fake = FakeAnalyze(fail=RuntimeError("디코딩 실패"))
    fake.release.set()
    monkeypatch.setattr(vods_module, "analyze_vod", fake)
    vid = vod_id(a)

    client.post(f"/api/vods/{vid}/analyze", json={})
    job = wait_for(client, vid, "error")

    assert "디코딩 실패" in job["message"]


def test_idle_status_for_a_vod_without_a_job(env):
    client, a, *_ = env

    assert client.get(f"/api/vods/{vod_id(a)}/analyze").json()["state"] == "idle"


def test_missing_ffmpeg_blocks_analysis(env, monkeypatch):
    client, a, *_ = env
    monkeypatch.setattr(vods_module, "discover_ffmpeg", lambda: None)

    assert client.post(f"/api/vods/{vod_id(a)}/analyze", json={}).status_code == 503


def test_vod_wide_delete_removes_only_that_vods_clips(cat_env):
    client, a, resolved = cat_env
    vid = vod_id(a)
    ids = [write_cat_clip(resolved, vid, 1, 10, "자동 보관"), write_cat_clip(resolved, vid, 2, 10, "자동 보관")]
    other = write_cat_clip(resolved, "otherid00001", 1, 10, "자동 보관")

    assert client.delete(f"/api/vods/{vid}/clips").json()["count"] == 2
    assert not any((resolved.library_vod / f"{i}.json").exists() for i in ids)
    assert (resolved.library_vod / f"{other}.json").exists()


def test_vod_wide_delete_uses_the_configured_delete_mode(cat_env, monkeypatch):
    from lumia_briefing_room.pipeline import delete_helper

    client, a, resolved = cat_env
    vid = vod_id(a)
    write_cat_clip(resolved, vid, 1, 10, "자동 보관")
    client.put("/api/config", json={"ui": {"deleteMode": "recycle"}})
    sent = []
    monkeypatch.setattr(delete_helper, "_send2trash", lambda path: sent.append(Path(path).name))

    client.delete(f"/api/vods/{vid}/clips")

    assert sent  # 실제로 지우는 대신 재활용 함수가 불렸다


def test_vod_wide_delete_also_clears_the_games_summary_so_the_row_resets(env):
    """실사용 보고(2026-09-27): "전체 삭제" 뒤에도 게임 목록이 안 사라져 다시 통째로
    분석하려 해도 목록에 옛 게임 행이 계속 남았다 - 클립만 지우고 게임 요약은 그대로
    두면 클립 0개 행이 영원히 안 없어진다."""
    client, a, _, vod_dir, *_ = env
    vid = vod_id(a)
    write_vod_clip(vod_dir, vid, 1, 10)
    save_index(vod_dir, {
        "id": vid, "path": str(a), "status": "done", "decodeDone": True, "analyzedSec": 100.0,
        "games": [{"index": 1, "startSec": 0.0, "endSec": 10.0, "result": None, "clipIds": [f"vod_{vid}_g01_000010"]}],
        "clips": [f"vod_{vid}_g01_000010"],
    })

    client.delete(f"/api/vods/{vid}/clips")

    entry = by_id(client.get("/api/vods"))[vid]
    assert entry["status"] == "new" and entry["games"] == []
    from lumia_briefing_room.pipeline.vod_store import load_index as _load_index
    saved = _load_index(vod_dir, vid)
    assert saved["decodeDone"] is True and saved["analyzedSec"] == 100.0


def test_delete_vod_entirely_removes_index_cache_and_clips(cat_env):
    """"게임 항목"(색인) 자체를 지운다 - `DELETE .../clips`(전체 삭제)는 색인을 남기고
    games/clips 만 비우지만, 이건 색인 파일과 판독 캐시까지 지운다."""
    from lumia_briefing_room.pipeline.vod_store import cache_path, index_path

    client, a, resolved = cat_env
    vod_dir = resolved.library_vod
    vid = vod_id(a)
    cid = write_cat_clip(resolved, vid, 1, 10, "자동 보관")
    save_index(vod_dir, {"id": vid, "path": str(a), "status": "done", "games": [], "clips": [cid]})
    cache_path(vod_dir, vid).parent.mkdir(parents=True, exist_ok=True)
    cache_path(vod_dir, vid).write_bytes(b"cache")

    resp = client.delete(f"/api/vods/{vid}")

    assert resp.status_code == 200 and resp.json()["deletedClips"] == 1
    assert not (vod_dir / f"{cid}.json").exists()
    assert not index_path(vod_dir, vid).exists()
    assert not cache_path(vod_dir, vid).exists()


def test_delete_vod_disappears_from_the_list_once_the_source_is_also_gone(env):
    """실사용 보고(2026-09-29): 원본 영상도 "성공 시 원본 삭제"로 지워지고 클립도 전체
    삭제했는데, 색인만 남아 "분석 안 함" 행이 목록에서 영원히 안 없어졌다."""
    client, a, _, vod_dir, *_ = env
    vid = vod_id(a)
    save_index(vod_dir, {
        "id": vid, "path": str(a), "status": "new", "games": [], "clips": [], "sourceDeleted": True,
    })
    a.unlink()

    resp = client.delete(f"/api/vods/{vid}")

    assert resp.status_code == 200
    assert vid not in by_id(client.get("/api/vods"))


def test_delete_vod_reappears_as_new_when_the_source_file_still_exists(env):
    """원본이 아직 있으면 다음 목록 조회 때 `discover_videos` 가 다시 찾아 "분석 안 함"으로
    나타난다 - 색인만 지웠을 뿐 원본 파일은 건드리지 않는다."""
    client, a, _, vod_dir, *_ = env
    vid = vod_id(a)
    save_index(vod_dir, {"id": vid, "path": str(a), "status": "done", "games": [], "clips": []})

    client.delete(f"/api/vods/{vid}")

    entry = by_id(client.get("/api/vods"))[vid]
    assert entry["status"] == "new" and entry["exists"] is True


def test_delete_vod_is_blocked_while_that_vod_is_analyzing(env, monkeypatch):
    client, a, *_ = env
    fake = FakeAnalyze()
    monkeypatch.setattr(vods_module, "analyze_vod", fake)
    vid = vod_id(a)
    client.post(f"/api/vods/{vid}/analyze", json={})
    assert fake.started.wait(2)

    assert client.delete(f"/api/vods/{vid}").status_code == 409

    fake.release.set()
    wait_for(client, vid, "done")


def test_delete_vod_unknown_id_is_404(env):
    client, *_ = env
    assert client.delete("/api/vods/does-not-exist").status_code == 404


def test_delete_vod_game_removes_it_and_deletes_its_clips(cat_env, monkeypatch):
    from lumia_briefing_room.pipeline import delete_helper

    client, a, resolved = cat_env
    vid = vod_id(a)
    cid = write_cat_clip(resolved, vid, 1, 10, "자동 보관")
    save_index(resolved.library_vod, {
        "id": vid, "path": str(a), "status": "done",
        "games": [
            {"index": 1, "startSec": 0.0, "endSec": 10.0, "result": None, "clipIds": [cid]},
            {"index": 2, "startSec": 20.0, "endSec": 30.0, "result": None, "clipIds": []},
        ],
        "clips": [cid],
    })
    sent = []
    monkeypatch.setattr(delete_helper, "_send2trash", lambda path: sent.append(Path(path).name))

    resp = client.delete(f"/api/vods/{vid}/games/1")

    assert resp.status_code == 200 and resp.json()["deletedClips"] == 1
    assert sent  # 설정된 삭제 방식(기본 recycle)으로 실제 클립 파일이 지워졌다
    entry = by_id(client.get("/api/vods"))[vid]
    assert [g["index"] for g in entry["games"]] == [2]


def test_delete_vod_game_works_with_zero_clips(env):
    """클립이 없는 게임(교전은 못 뽑았지만 결과 화면은 읽은 경우, plan.md §10-6)도
    지울 수 있어야 한다 - 클립 기준 삭제 경로로는 지울 방법이 없었다."""
    client, a, _, vod_dir, *_ = env
    vid = vod_id(a)
    save_index(vod_dir, {
        "id": vid, "path": str(a), "status": "done",
        "games": [{"index": 1, "startSec": 0.0, "endSec": 10.0, "result": None, "clipIds": []}],
        "clips": [],
    })

    resp = client.delete(f"/api/vods/{vid}/games/1")

    assert resp.status_code == 200 and resp.json()["deletedClips"] == 0
    assert by_id(client.get("/api/vods"))[vid]["games"] == []


def test_delete_vod_game_404s_for_unknown_game_or_vod(env):
    client, a, _, vod_dir, *_ = env
    vid = vod_id(a)
    save_index(vod_dir, {
        "id": vid, "path": str(a), "status": "done",
        "games": [{"index": 1, "startSec": 0.0, "endSec": 10.0, "result": None, "clipIds": []}],
        "clips": [],
    })

    assert client.delete(f"/api/vods/{vid}/games/99").status_code == 404
    assert client.delete(f"/api/vods/does-not-exist/games/1").status_code == 404


def test_fs_videos_lists_folders_and_only_video_files(env):
    client, _, _, _, _, videos = env

    data = client.get("/api/fs/videos", params={"path": str(videos)}).json()

    assert data["dirs"] == ["sub"]
    assert [f["name"] for f in data["files"]] == ["a.mp4"]
    assert data["files"][0]["sizeBytes"] == 3000
    assert client.get("/api/fs/videos", params={"path": str(videos / "nope")}).status_code == 404
    assert client.get("/api/fs/videos").json()["dirs"]


def test_listing_does_not_wait_for_slow_duration_probes_and_reports_probing(env, monkeypatch):
    client, a, b, *_ = env
    release = threading.Event()
    probed = []

    def slow_probe(path, ffmpeg):
        probed.append(path.name)
        release.wait(5)
        return VideoInfo(width=1, height=1, fps=1.0, duration_sec=1234.5, codec="h264")

    monkeypatch.setattr(vods_module, "_probe_info", slow_probe)
    started = time.time()
    first = by_id(client.get("/api/vods"))
    assert time.time() - started < 2
    assert all(entry["probing"] and entry["durationSec"] is None for entry in first.values())

    release.set()
    deadline = time.time() + 5
    while time.time() < deadline:
        second = by_id(client.get("/api/vods"))
        if not any(entry["probing"] for entry in second.values()):
            break
        time.sleep(0.05)
    assert all(entry["durationSec"] == 1234.5 and not entry["probing"] for entry in second.values())
    assert sorted(probed) == ["a.mp4"]

    client.get("/api/vods")
    assert sorted(probed) == ["a.mp4"]


def test_indexed_vods_and_missing_files_are_never_probed(env, monkeypatch):
    client, a, b, vod_dir, *_ = env
    vid = vod_id(a)
    save_index(vod_dir, {"id": vid, "path": str(a), "status": "done", "durationSec": 99.0, "games": [], "clips": []})
    probed = []
    monkeypatch.setattr(vods_module, "_probe_info", lambda path, ffmpeg: probed.append(path.name))
    entry = by_id(client.get("/api/vods"))[vid]
    time.sleep(0.3)
    assert entry["durationSec"] == 99.0 and entry["probing"] is False
    assert "a.mp4" not in probed


def test_a_missing_file_is_not_probing(env):
    client, a, b, vod_dir, *_ = env
    vid = vod_id(a)
    save_index(vod_dir, {"id": vid, "path": str(a), "status": "done", "durationSec": 5.0, "games": [], "clips": []})
    a.unlink()
    entry = by_id(client.get("/api/vods"))[vid]
    assert entry["exists"] is False and entry["probing"] is False


@pytest.fixture
def cat_env(tmp_path, monkeypatch):
    """카테고리 폴더 저장소: 영상 클립 영상은 `clips\<카테고리>\`, 정보는 library_vod."""
    monkeypatch.setattr(vods_module, "discover_ffmpeg", lambda: tmp_path / "ffmpeg.exe")
    monkeypatch.setattr(vods_module, "_probe_info", lambda path, ffmpeg: None)
    videos = tmp_path / "videos"
    a = write_video(videos / "a.mp4", b"A" * 3000)
    cfg = Config(paths=PathsConfig(root=tmp_path / "store", temp=tmp_path / "tmp"))
    resolved = resolve_paths(cfg.paths)
    cfg.vod.sources = [str(videos)]
    config_path = tmp_path / "config.json"
    from lumia_briefing_room.config import save_config
    save_config(cfg, config_path)
    return TestClient(create_app(cfg, config_path=config_path)), a, resolved


def write_cat_clip(resolved, vid: str, game: int, start: int, category: str):
    cid = write_vod_clip(resolved.library_vod, vid, game, start)
    (resolved.library_vod / f"{cid}.mp4").unlink()
    folder = resolved.clips_root / category
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{cid}.mp4").write_bytes(b"x" * 100)
    return cid


def seed_mixed_vod(resolved, a):
    vid = vod_id(a)
    auto = write_cat_clip(resolved, vid, 1, 10, "자동 보관")
    kept = write_cat_clip(resolved, vid, 1, 90, "아야")
    kept2 = write_cat_clip(resolved, vid, 2, 10, "보관함")
    save_index(resolved.library_vod, {
        "id": vid, "path": str(a), "status": "done", "decodeDone": True, "analyzedSec": 100.0,
        "games": [{"index": 1, "startSec": 0.0, "endSec": 10.0, "result": None, "clipIds": [auto, kept]},
                  {"index": 2, "startSec": 20.0, "endSec": 30.0, "result": None, "clipIds": [kept2]}],
        "clips": [auto, kept, kept2],
    })
    return vid, auto, kept, kept2


def listed_clip_ids(client):
    return {c["id"] for c in client.get("/api/clips", params={"source": "vod"}).json()}


def test_vod_wide_delete_removes_only_auto_archive_clips_and_keeps_user_archived_ones(cat_env):
    client, a, resolved = cat_env
    vid, auto, kept, kept2 = seed_mixed_vod(resolved, a)

    body = client.delete(f"/api/vods/{vid}/clips").json()

    assert body["count"] == 1 and body["keptClips"] == 2
    assert listed_clip_ids(client) == {kept, kept2}, "남은 클립은 클립 탭에 그대로 보인다"
    assert client.get(f"/api/clips/{kept}").status_code == 200
    assert client.get(f"/api/clips/{kept}/video").status_code in (200, 206)
    assert by_id(client.get("/api/vods"))[vid]["status"] == "new", "분석 결과는 그대로 비워진다"
    assert client.delete(f"/api/clips/{kept}").status_code == 200
    assert listed_clip_ids(client) == {kept2}


def test_delete_vod_entirely_keeps_user_archived_clips_visible_in_the_clip_tab(cat_env):
    from lumia_briefing_room.pipeline.vod_store import index_path

    client, a, resolved = cat_env
    vid, auto, kept, kept2 = seed_mixed_vod(resolved, a)

    body = client.delete(f"/api/vods/{vid}").json()

    assert body["deletedClips"] == 1 and body["keptClips"] == 2
    assert not index_path(resolved.library_vod, vid).exists()
    assert listed_clip_ids(client) == {kept, kept2}
    assert client.get(f"/api/clips/{kept2}").status_code == 200


def test_delete_vod_game_keeps_user_archived_clips_of_that_game(cat_env):
    client, a, resolved = cat_env
    vid, auto, kept, kept2 = seed_mixed_vod(resolved, a)

    body = client.delete(f"/api/vods/{vid}/games/1").json()

    assert body["deletedClips"] == 1 and body["keptClips"] == 1
    assert listed_clip_ids(client) == {kept, kept2}
    assert [g["index"] for g in by_id(client.get("/api/vods"))[vid]["games"]] == [2]


def test_vod_deletes_remove_everything_when_all_clips_are_auto_archive(cat_env):
    client, a, resolved = cat_env
    vid = vod_id(a)
    ids = [write_cat_clip(resolved, vid, 1, 10, "자동 보관"), write_cat_clip(resolved, vid, 1, 90, "자동 보관")]
    save_index(resolved.library_vod, {"id": vid, "path": str(a), "status": "done", "games": [], "clips": ids})

    body = client.delete(f"/api/vods/{vid}/clips").json()

    assert body["count"] == 2 and body["keptClips"] == 0 and listed_clip_ids(client) == set()


def test_legacy_layout_vod_clips_survive_every_vod_delete(env):
    client, a, _, vod_dir, *_ = env
    vid = vod_id(a)
    cid = write_vod_clip(vod_dir, vid, 1, 10)
    save_index(vod_dir, {"id": vid, "path": str(a), "status": "done",
                         "games": [{"index": 1, "startSec": 0.0, "endSec": 10.0, "result": None, "clipIds": [cid]}],
                         "clips": [cid]})

    assert client.delete(f"/api/vods/{vid}/games/1").json()["keptClips"] == 1
    assert client.delete(f"/api/vods/{vid}/clips").json()["count"] == 0
    assert client.delete(f"/api/vods/{vid}").json()["deletedClips"] == 0
    assert (vod_dir / f"{cid}.json").exists() and (vod_dir / f"{cid}.mp4").exists()
