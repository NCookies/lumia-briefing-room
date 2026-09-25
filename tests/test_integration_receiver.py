"""실제 수신 서버 컨테이너(infra 저장소의 receiver 이미지)에 앱의 전송 클라이언트를 붙이는 통합 테스트.

기본 실행에서는 빠진다. 도커가 켜져 있고 infra 저장소가 이 저장소 옆(`../infra`)에 있을 때:

    pytest -m integration tests/test_integration_receiver.py

운영 서버에는 접속하지 않는다(임시 컨테이너, 임시 토큰).
"""

import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest

from lumia_briefing_room.config import Config, dataclass_from_camel_dict, load_config, save_config
from lumia_briefing_room.telemetry.outbox import Outbox
from lumia_briefing_room.telemetry.sender import DAY, TelemetrySender

pytestmark = pytest.mark.integration

RECEIVER_DIR = Path(__file__).resolve().parents[2] / "infra" / "services" / "receiver"
UPLOAD_TOKEN = "it-upload-token"
ADMIN_TOKEN = "it-admin-token"


def _docker_ok() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@pytest.fixture(scope="module")
def server():
    if not RECEIVER_DIR.is_dir():
        pytest.skip("infra 저장소(../infra)가 없다")
    if not _docker_ok():
        pytest.skip("도커를 쓸 수 없다")
    tag = "lumia-receiver:integration"
    subprocess.run(["docker", "build", "-q", "-t", tag, str(RECEIVER_DIR)], check=True, capture_output=True)
    name = f"lumia-it-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        ["docker", "run", "-d", "--name", name, "-p", "127.0.0.1::8000",
         "-e", f"API_TOKEN={UPLOAD_TOKEN}", "-e", f"ADMIN_TOKEN={ADMIN_TOKEN}", "-e", "RATE_LIMIT_FAILURES=50", tag],
        check=True, capture_output=True,
    )
    try:
        port = subprocess.run(["docker", "port", name, "8000/tcp"], check=True, capture_output=True, text=True).stdout
        url = f"http://127.0.0.1:{port.strip().splitlines()[0].rsplit(':', 1)[1]}"
        for _ in range(60):
            try:
                if httpx.get(f"{url}/healthz", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            raise RuntimeError("컨테이너가 시작되지 않았다")
        yield url
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


class Env:
    def __init__(self, tmp_path, url, token=UPLOAD_TOKEN):
        self.tmp, self.url = tmp_path, url
        self.config_path = tmp_path / "config.json"
        self.clips = tmp_path / "clips"
        self.clips.mkdir()
        (tmp_path / "vod").mkdir()
        self.outbox = Outbox(tmp_path / "outbox.jsonl")
        self.clock_now = 1_000_000.0
        cfg = dataclass_from_camel_dict(Config, {
            "paths": {"clips": str(self.clips), "vodClips": str(tmp_path / "vod")},
            "player": {"nickname": "테스트닉"},
            "telemetry": {"sendLabels": True, "sendLogs": True, "apiToken": token, "serverUrl": url},
        })
        save_config(cfg, self.config_path)

    def sender(self):
        return TelemetrySender(
            config_path=self.config_path, state_path=self.tmp / "state.json", outbox=self.outbox,
            clock=lambda: self.clock_now, frozen=True, usernames=["tester"],
            collect_env=lambda cfg: {"appVersion": "0.1.1", "os": "Windows 11", "resolution": "2560x1440"},
        )

    def add_clip(self, clip_id, **over):
        meta = {"title": "제목", "sessionDir": "bg_1049590_x", "matchStartUtc": "2026-09-20T12:05:30Z", "userLabel": "pvp",
                "gameMode": "battle_royale", "sourceWidth": 2560, "sourceHeight": 1440, "pvpScore": 1.0,
                "pvpSignals": ["kill_delta"], "killDelta": 1, "myCharacter": "아야"}
        meta.update(over)
        (self.clips / f"{clip_id}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def exported(url):
    response = httpx.get(f"{url}/v1/admin/labels", headers={"X-Admin-Token": ADMIN_TOKEN}, timeout=10)
    assert response.status_code == 200
    return response.json()["labels"]


def test_labels_and_logs_reach_the_real_server_and_can_be_pulled_and_deleted(tmp_path, server):
    env = Env(tmp_path, server)
    env.add_clip("c1", labelNote="3인 교전")
    env.add_clip("c2", userLabel="pve")
    env.outbox.append({"ts": "2026-09-25T00:00:00Z", "level": "ERROR", "logger": "lumia_briefing_room.x",
                       "message": r"열 수 없다 C:\Users\tester\a.mp4 테스트닉", "exceptionType": "OSError",
                       "stack": 'File "C:\\Users\\tester\\x\\lumia_briefing_room\\a.py", line 3, in f\nOSError: x'})
    sender = env.sender()

    report = sender.run_once()
    assert report["labels"]["status"] == "sent" and report["labels"]["count"] == 2
    assert report["logs"]["status"] == "sent" and env.outbox.read() == []

    install_id = load_config(env.config_path).telemetry.install_id
    mine = [item for item in exported(server) if item["installId"] == install_id]
    assert sorted(i["label"]["userLabel"] for i in mine) == ["combat", "other"]
    assert any(i["label"].get("labelNote") == "3인 교전" for i in mine)
    assert all("제목" not in json.dumps(i, ensure_ascii=False) for i in mine)

    env.add_clip("c1", userLabel="pve", labelNote="고침")
    env.clock_now += DAY + 1
    sender.run_once()
    after = [item for item in exported(server) if item["installId"] == install_id]
    assert len(after) == 2, "라벨을 고쳐 다시 보내도 서버에 중복 저장되면 안 된다"
    assert sorted(i["label"]["userLabel"] for i in after) == ["other", "other"]

    result = sender.delete_remote()
    assert result["ok"] is True and result["deleted"] is True
    assert [item for item in exported(server) if item["installId"] == install_id] == []
    cfg = load_config(env.config_path)
    assert cfg.telemetry.send_labels is False and cfg.telemetry.send_logs is False


def test_pull_labels_tool_reads_what_the_client_sent(tmp_path, server, monkeypatch):
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("pull_labels_it", Path(__file__).resolve().parents[1] / "tools" / "pull_labels.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["pull_labels_it"] = module
    spec.loader.exec_module(module)

    (tmp_path / "app").mkdir()
    env = Env(tmp_path / "app", server)
    env.add_clip("p1")
    env.sender().run_once()
    monkeypatch.setenv("LUMIA_ADMIN_TOKEN", ADMIN_TOKEN)
    out = tmp_path / "pulled"
    code = module.main(["--out", str(out), "--url", server, "--full"])
    assert code == 0
    files = list((out / ".labels").glob("*.json"))
    assert files and all(json.loads(p.read_text(encoding="utf-8"))["userLabel"] in ("pvp", "pve") for p in files)


def test_wrong_token_is_a_quiet_retry_not_a_crash(tmp_path, server):
    env = Env(tmp_path, server, token="wrong-token")
    env.add_clip("w1")
    report = env.sender().run_once()
    assert report["labels"]["status"] == "retry"
    assert report["labels"]["httpStatus"] == 401


def test_dev_mode_data_lands_apart_from_release_data(tmp_path, server):
    env = Env(tmp_path, server)
    cfg = load_config(env.config_path)
    cfg.app.mode = "dev"
    cfg.telemetry.allow_dev_send = True
    save_config(cfg, env.config_path)
    env.add_clip("d1")
    sender = TelemetrySender(config_path=env.config_path, state_path=tmp_path / "s.json", outbox=env.outbox,
                             frozen=False, collect_env=lambda c: {"appVersion": "0.1.1", "os": "x"})
    assert sender.run_once()["labels"]["status"] == "sent"
    install_id = load_config(env.config_path).telemetry.install_id
    release = [i for i in exported(server) if i["installId"] == install_id]
    dev = httpx.get(f"{server}/v1/admin/labels?mode=dev", headers={"X-Admin-Token": ADMIN_TOKEN}, timeout=10).json()["labels"]
    assert release == [] and any(i["installId"] == install_id for i in dev)


def test_diagnostics_send_returns_distinct_receipt_ids(tmp_path, server):
    import re

    env = Env(tmp_path, server)
    sender = env.sender()
    first = sender.send_diagnostics()
    second = sender.send_diagnostics()
    assert first["ok"] is True and second["ok"] is True
    pattern = re.compile(r"^R-\d{8}-[0-9A-Z]{6}$")
    assert pattern.match(first["receiptId"]) and pattern.match(second["receiptId"])
    assert first["receiptId"] != second["receiptId"]
