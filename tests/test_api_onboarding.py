import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lumia_briefing_room.api import onboarding as onboarding_module
from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.config import Config, PathsConfig, PlayerConfig, load_config
from lumia_briefing_room.consent import CONSENT_VERSION

MPD = """<?xml version="1.0" encoding="utf-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="PT10M" maxSegmentDuration="PT3.0S">
  <Period id="0" start="PT0S"><AdaptationSet id="0" contentType="video" maxWidth="{w}" maxHeight="{h}">
    <Representation id="0" mimeType="video/mp4" codecs="hev1.2.4.L123.B0" width="{w}" height="{h}">
      <SegmentTemplate timescale="1000000" duration="3000000" initialization="i" media="m" startNumber="1" />
    </Representation></AdaptationSet></Period>
</MPD>"""


@pytest.fixture(autouse=True)
def no_real_steam(monkeypatch):
    monkeypatch.setattr(onboarding_module, "discover_recording_root", lambda: None)


def _make(tmp_path: Path, **kwargs):
    config_path = tmp_path / "config.json"
    cfg = Config(paths=PathsConfig(clips=tmp_path / "clips", temp=tmp_path / "tmp", **kwargs))
    app = create_app(cfg, config_path=config_path)
    app.state.log_dir = tmp_path / "logs"
    return TestClient(app), config_path, app


def _recording(tmp_path: Path, w: int, h: int) -> Path:
    root = tmp_path / "steam" / "video"
    session = root / "bg_1049590_20260923_095917"
    session.mkdir(parents=True)
    (session / "session.mpd").write_text(MPD.format(w=w, h=h), encoding="utf-8")
    return root


def test_first_run_needed_until_completed(tmp_path: Path):
    client, config_path, _ = _make(tmp_path)
    body = client.get("/api/first-run").json()
    assert body["needed"] is True
    assert body["currentVersion"] == CONSENT_VERSION
    assert body["pendingItems"] == ["setup"]
    assert body["recording"]["root"] is None
    assert body["recording"]["session"] is None
    assert body["clipsDir"] == str(tmp_path / "clips")

    done = client.post("/api/first-run/complete").json()
    assert done["consentVersion"] == CONSENT_VERSION
    assert load_config(config_path).consent.version == CONSENT_VERSION
    assert client.get("/api/first-run").json()["needed"] is False


def test_first_run_reports_recording_folder_and_resolution(tmp_path: Path):
    root = _recording(tmp_path, 2560, 1440)
    client, _, _ = _make(tmp_path, steam_recording=root)
    recording = client.get("/api/first-run").json()["recording"]
    assert recording["root"] == str(root)
    assert recording["source"] == "config"
    assert recording["exists"] is True
    assert recording["session"]["width"] == 2560
    assert recording["session"]["codec"].startswith("hev1")
    assert recording["resolution"]["kind"] == "measured"


def test_first_run_flags_unsupported_aspect_ratio(tmp_path: Path):
    root = _recording(tmp_path, 3440, 1440)
    client, _, _ = _make(tmp_path, steam_recording=root)
    assert client.get("/api/first-run").json()["recording"]["resolution"]["kind"] == "unsupported_ratio"


def test_first_run_uses_auto_detected_root(tmp_path: Path, monkeypatch):
    root = _recording(tmp_path, 1920, 1080)
    monkeypatch.setattr(onboarding_module, "discover_recording_root", lambda: root)
    client, _, _ = _make(tmp_path)
    recording = client.get("/api/first-run").json()["recording"]
    assert recording["source"] == "auto"
    assert recording["resolution"]["kind"] == "measured"


def test_first_run_reports_missing_folder(tmp_path: Path):
    client, _, _ = _make(tmp_path, steam_recording=tmp_path / "nope")
    recording = client.get("/api/first-run").json()["recording"]
    assert recording["exists"] is False and recording["session"] is None


def test_complete_keeps_newer_answered_version(tmp_path: Path):
    client, config_path, _ = _make(tmp_path)
    client.put("/api/config", json={"consent": {"version": CONSENT_VERSION + 3}})
    assert client.post("/api/first-run/complete").json()["consentVersion"] == CONSENT_VERSION + 3


def test_diagnostics_zip_is_scrubbed_download(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERNAME", "tester")
    root = _recording(tmp_path, 2560, 1440)
    client, config_path, app = _make(tmp_path, steam_recording=root)
    app.state.config.player = PlayerConfig(nickname="테스트닉")
    client.put("/api/config", json={"player": {"nickname": "테스트닉"}})
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "app.log").write_text("INFO 테스트닉 C:/Users/tester/x", encoding="utf-8")

    resp = client.get("/api/diagnostics")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    assert ".zip" in resp.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = set(zf.namelist())
        texts = {n: zf.read(n).decode("utf-8") for n in names}
    assert {"info.json", "config.json", "logs/app.log"} <= names
    for name, text in texts.items():
        assert "테스트닉" not in text and "tester" not in text, name
    info = json.loads(texts["info.json"])
    assert info["version"]
    assert info["mode"] in ("dev", "release")
    assert info["recording"]["resolution"]["kind"] == "measured"
    assert info["recording"]["session"]["codec"].startswith("hev1")


def test_first_run_accepts_the_parent_folder_the_friend_picked(tmp_path: Path):
    """친구가 스팀 선택 창에서 gamerecordings(한 단계 위)를 골라도 video 로 바로잡아 인식한다."""
    video = _recording(tmp_path, 2560, 1440)
    parent = video.parent
    client, _, _ = _make(tmp_path, steam_recording=parent)

    recording = client.get("/api/first-run").json()["recording"]

    assert recording["root"] == str(video)
    assert recording["session"]["width"] == 2560
