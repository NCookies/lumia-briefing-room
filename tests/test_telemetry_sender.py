import json
import threading
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from jsonschema import Draft202012Validator

from lumia_briefing_room.config import Config, dataclass_from_camel_dict, load_config, save_config
from lumia_briefing_room.telemetry.client import ReceiverClient
from lumia_briefing_room.telemetry.outbox import Outbox
from lumia_briefing_room.telemetry.sender import DAY, TelemetrySender

CONTRACT = Path(__file__).resolve().parent / "contract"
SCHEMA = json.loads((CONTRACT / "receiver.schema.json").read_text(encoding="utf-8"))


def validate(name, payload):
    return list(Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]}).iter_errors(payload))


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Env:
    """설정·클립·outbox·가짜 서버를 한 묶음으로 만든 테스트 환경."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.config_path = tmp_path / "config.json"
        self.clips = tmp_path / "clips"
        self.vod = tmp_path / "vod"
        self.clips.mkdir()
        self.vod.mkdir()
        self.outbox = Outbox(tmp_path / "outbox" / "errors.jsonl")
        self.recent = Outbox(tmp_path / "outbox" / "errors_recent.jsonl")
        self.clock = Clock()
        self.calls: list[httpx.Request] = []
        self.responses: list = []
        self.factory_calls = 0
        self.nickname = "테스트닉"
        self.configure()

    def configure(self, *, labels=True, logs=True, token="tok", allow_dev=False, mode="auto", url="https://r.example"):
        cfg = dataclass_from_camel_dict(Config, {
            "app": {"mode": mode},
            "paths": {"clips": str(self.clips), "vodClips": str(self.vod)},
            "player": {"nickname": self.nickname},
            "telemetry": {"sendLabels": labels, "sendLogs": logs, "apiToken": token, "serverUrl": url,
                          "allowDevSend": allow_dev},
        })
        save_config(cfg, self.config_path)

    def add_clip(self, clip_id, root=None, **over):
        meta = {
            "title": "제목", "sessionDir": "bg_1049590_20260920_120101", "matchStartUtc": "2026-09-20T12:05:30Z",
            "gameMode": "battle_royale", "sourceWidth": 2560, "sourceHeight": 1440, "durationSec": 27.0,
            "userLabel": "pvp", "killDelta": 1, "pvpScore": 0.9, "pvpSignals": ["kill_delta"], "tags": [],
        }
        meta.update(over)
        (root or self.clips).joinpath(f"{clip_id}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    def respond(self, *responses):
        self.responses = list(responses)

    def _handler(self, request):
        self.calls.append(request)
        if self.responses:
            item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
            if isinstance(item, Exception):
                raise item
            return httpx.Response(item, json=self._ok(request) if item == 200 else {"detail": "x"})
        return httpx.Response(200, json=self._ok(request))

    @staticmethod
    def _ok(request):
        if request.url.path == "/v1/diagnostics":
            return {"receiptId": "R-20260925-K7M3QX", "saved": len(json.loads(request.content)["entries"])}
        return {"saved": 1}

    def sender(self, *, frozen=True):
        def factory(endpoint):
            self.factory_calls += 1
            return ReceiverClient(endpoint, transport=httpx.MockTransport(self._handler))

        return TelemetrySender(
            config_path=self.config_path, state_path=self.tmp / "state.json", outbox=self.outbox, recent=self.recent,
            client_factory=factory, clock=self.clock, frozen=frozen,
            collect_env=lambda cfg: {"appVersion": "0.1.1", "os": "Windows 11", "resolution": "2560x1440"},
            usernames=["tester"],
        )

    def bodies(self, path):
        return [json.loads(r.content) for r in self.calls if r.url.path == path]


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


# ── 동의·모드·엔드포인트 게이트 ────────────────────────────────────────


def test_no_network_call_at_all_when_both_consents_are_off(env):
    env.configure(labels=False, logs=False)
    env.add_clip("c1")
    env.outbox.append({"ts": "t", "level": "ERROR", "message": "m"})
    report = env.sender().run_once()
    assert env.calls == [] and env.factory_calls == 0
    assert report["labels"]["status"] == "off" and report["logs"]["status"] == "off"


def test_only_the_enabled_kind_is_sent(env):
    env.configure(labels=True, logs=False)
    env.add_clip("c1")
    env.outbox.append({"ts": "t", "level": "ERROR", "message": "m"})
    env.sender().run_once()
    assert {r.url.path for r in env.calls} == {"/v1/labels"}
    assert len(env.outbox.read()) == 1


def test_dev_mode_never_sends_unless_explicitly_allowed(env):
    env.add_clip("c1")
    env.sender(frozen=False).run_once()
    assert env.calls == [] and env.factory_calls == 0
    env.configure(allow_dev=True)
    env.sender(frozen=False).run_once()
    assert env.bodies("/v1/labels")[0]["mode"] == "dev"


def test_explicit_release_mode_setting_sends_as_release_even_from_source(env):
    env.configure(mode="release")
    env.add_clip("c1")
    env.sender(frozen=False).run_once()
    assert env.bodies("/v1/labels")[0]["mode"] == "release"


def test_release_build_sends_release_mode(env):
    env.add_clip("c1")
    env.sender(frozen=True).run_once()
    assert env.bodies("/v1/labels")[0]["mode"] == "release"


def test_without_a_token_nothing_is_sent(env, monkeypatch):
    monkeypatch.delenv("LUMIA_RECEIVER_TOKEN", raising=False)
    monkeypatch.setattr("lumia_briefing_room.telemetry.endpoint.bundled_endpoint", lambda: {})
    env.configure(token="")
    env.add_clip("c1")
    report = env.sender().run_once()
    assert env.calls == [] and report["labels"]["status"] == "no-endpoint"


def test_install_id_is_created_once_and_persisted(env):
    env.add_clip("c1")
    env.sender().run_once()
    first = load_config(env.config_path).telemetry.install_id
    assert UUID(first)
    env.clock.advance(DAY + 1)
    env.add_clip("c2")
    env.sender().run_once()
    assert load_config(env.config_path).telemetry.install_id == first
    assert all(b["installId"] == first for b in env.bodies("/v1/labels"))


# ── 라벨 전송 ────────────────────────────────────────────────────────


def test_label_payload_follows_the_contract_and_converts_local_values(env):
    env.add_clip("c1", userLabel="pvp", labelNote="메모")
    env.add_clip("c2", userLabel="pve")
    env.add_clip("c3", userLabel=None)
    env.sender().run_once()
    (body,) = env.bodies("/v1/labels")
    assert validate("LabelBatch", body) == []
    assert sorted(l["userLabel"] for l in body["labels"]) == ["combat", "other"]
    assert body["schemaVersion"] == 1 and body["appVersion"]
    assert "제목" not in json.dumps(body, ensure_ascii=False)


def test_vod_clip_labels_are_included_with_source_vod(env):
    env.add_clip("vod_abc_g01_000010", root=env.vod, source="vod", vodId="abc", vodGameIndex=1, streamer="스트리머",
                 vodFile="H:/a.mp4", sessionDir=None, matchStartUtc=None)
    env.sender().run_once()
    (body,) = env.bodies("/v1/labels")
    assert body["labels"][0]["source"] == "vod" and "스트리머" not in json.dumps(body, ensure_ascii=False)


def test_archived_labels_of_deleted_clips_are_sent_too_and_live_clips_win(env):
    archive = env.clips / ".labels"
    archive.mkdir()
    (archive / "gone1.json").write_text(json.dumps({"id": "gone1", "userLabel": "pve", "matchStartUtc": "x", "sessionDir": "s"}), encoding="utf-8")
    (archive / "c1.json").write_text(json.dumps({"id": "c1", "userLabel": "pve"}), encoding="utf-8")
    env.add_clip("c1", userLabel="pvp")
    env.sender().run_once()
    labels = env.bodies("/v1/labels")[0]["labels"]
    assert len(labels) == 2 and sorted(l["userLabel"] for l in labels) == ["combat", "other"]


def test_trashed_clips_are_not_sent(env):
    trash = env.clips / ".trash"
    trash.mkdir()
    env.add_clip("t1", root=trash)
    env.sender().run_once()
    assert env.calls == []


def test_unchanged_labels_are_not_resent_but_changes_are_with_the_same_key(env):
    env.add_clip("c1", userLabel="pvp")
    sender = env.sender()
    sender.run_once()
    first_key = env.bodies("/v1/labels")[0]["labels"][0]["clipKey"]
    env.clock.advance(DAY + 1)
    sender.run_once()
    assert len(env.bodies("/v1/labels")) == 1
    env.add_clip("c1", userLabel="pve", labelNote="고침")
    env.clock.advance(DAY + 1)
    sender.run_once()
    second = env.bodies("/v1/labels")[1]["labels"][0]
    assert second["clipKey"] == first_key and second["userLabel"] == "other" and second["labelNote"] == "고침"


def test_title_or_pin_changes_do_not_trigger_a_resend(env):
    env.add_clip("c1")
    sender = env.sender()
    sender.run_once()
    env.add_clip("c1", title="다른 제목", pinned=True)
    env.clock.advance(DAY + 1)
    sender.run_once()
    assert len(env.bodies("/v1/labels")) == 1


def test_sends_at_most_once_a_day_unless_forced(env):
    env.add_clip("c1")
    sender = env.sender()
    sender.run_once()
    env.add_clip("c2")
    env.clock.advance(3600)
    sender.run_once()
    assert len(env.bodies("/v1/labels")) == 1
    sender.run_once(force=True)
    assert len(env.bodies("/v1/labels")) == 2
    env.add_clip("c3")
    env.clock.advance(DAY + 1)
    sender.run_once()
    assert len(env.bodies("/v1/labels")) == 3


def test_large_backlog_is_split_into_batches_of_at_most_200(env):
    for i in range(450):
        env.add_clip(f"c{i:04d}")
    env.sender().run_once()
    sizes = [len(b["labels"]) for b in env.bodies("/v1/labels")]
    assert sizes == [200, 200, 50]


def test_a_failure_midway_keeps_what_was_confirmed_and_retries_the_rest(env):
    for i in range(450):
        env.add_clip(f"c{i:04d}")
    env.respond(200, 500)
    sender = env.sender()
    sender.run_once()
    assert len(env.calls) == 2
    env.respond(200)
    env.calls.clear()
    env.clock.advance(15 * 60 + 1)
    sender.run_once()
    assert sum(len(b["labels"]) for b in env.bodies("/v1/labels")) == 250


# ── 실패·백오프 ────────────────────────────────────────────────────


@pytest.mark.parametrize("failure", [500, 502, 401, 429, httpx.ConnectTimeout("t"), httpx.ConnectError("refused")])
def test_server_trouble_never_raises_and_is_retried_later(env, failure):
    env.add_clip("c1")
    env.respond(failure)
    report = env.sender().run_once()
    assert report["labels"]["status"] == "retry"


def test_backoff_doubles_up_to_the_cap_and_resets_after_success(env):
    env.add_clip("c1")
    env.respond(500)
    sender = env.sender()
    sender.run_once()
    for minutes in [15, 30, 60, 120, 240, 360, 360]:
        env.clock.advance(minutes * 60 - 1)
        before = len(env.calls)
        sender.run_once()
        assert len(env.calls) == before, f"{minutes}분 전에 다시 시도했다"
        env.clock.advance(1)
        sender.run_once()
        assert len(env.calls) == before + 1, f"{minutes}분 뒤에 다시 시도하지 않았다"
    env.respond(200)
    env.clock.advance(6 * 3600)
    assert sender.run_once()["labels"]["status"] == "sent"


def test_retry_after_from_the_server_is_respected_when_longer(env):
    env.add_clip("c1")

    def handler(request):
        env.calls.append(request)
        return httpx.Response(429, json={}, headers={"Retry-After": "7200"})

    sender = env.sender()
    sender._client_factory = lambda endpoint: ReceiverClient(endpoint, transport=httpx.MockTransport(handler))
    sender.run_once()
    env.clock.advance(3600)
    sender.run_once()
    assert len(env.calls) == 1
    env.clock.advance(3700)
    sender.run_once()
    assert len(env.calls) == 2


@pytest.mark.parametrize("status", [413, 422])
def test_batches_the_server_will_never_accept_are_dropped_not_retried_forever(env, status):
    env.add_clip("c1")
    env.respond(status)
    sender = env.sender()
    report = sender.run_once()
    assert report["labels"]["status"] == "dropped"
    env.clock.advance(DAY + 1)
    sender.run_once()
    assert len(env.calls) == 1


def test_a_dropped_label_is_sent_again_once_its_content_changes(env):
    env.add_clip("c1")
    env.respond(422)
    sender = env.sender()
    sender.run_once()
    env.respond(200)
    env.add_clip("c1", labelNote="고침")
    env.clock.advance(DAY + 1)
    sender.run_once()
    assert len(env.calls) == 2


def test_a_server_outage_does_not_block_the_next_kind(env):
    env.add_clip("c1")
    env.outbox.append({"ts": "t", "level": "ERROR", "message": "m"})
    env.respond(500)
    report = env.sender().run_once()
    assert report["labels"]["status"] == "retry" and report["logs"]["status"] == "retry"
    assert {r.url.path for r in env.calls} == {"/v1/labels", "/v1/logs"}


# ── 오류 로그 ────────────────────────────────────────────────────────


def test_log_payload_is_scrubbed_follows_the_contract_and_clears_the_outbox(env):
    env.outbox.append({"ts": "2026-09-24T01:47:36Z", "level": "ERROR", "logger": "lumia_briefing_room.x",
                       "message": r"열 수 없다 C:\Users\tester\Videos\테스트닉\a.mp4", "exceptionType": "OSError",
                       "stack": 'Traceback\n  File "C:\\Users\\tester\\app\\lumia_briefing_room\\a.py", line 3, in f\nOSError: x'})
    env.sender().run_once()
    (body,) = env.bodies("/v1/logs")
    assert validate("LogBatch", body) == []
    blob = json.dumps(body, ensure_ascii=False)
    assert "tester" not in blob and "테스트닉" not in blob and "Videos" not in blob
    assert body["entries"][0]["fingerprint"] and body["env"]["appVersion"] == "0.1.1"
    assert env.outbox.read() == []


def test_failed_log_send_keeps_the_entries_and_new_ones_arriving_meanwhile(env):
    env.outbox.append({"ts": "t", "level": "ERROR", "message": "a"})
    env.respond(500)
    sender = env.sender()
    sender.run_once()
    env.outbox.append({"ts": "t", "level": "ERROR", "message": "b"})
    assert [e["message"] for e in env.outbox.read()] == ["a", "b"]
    env.respond(200)
    env.clock.advance(15 * 60 + 1)
    sender.run_once()
    assert [e["message"] for e in env.bodies("/v1/logs")[-1]["entries"]] == ["a", "b"]
    assert env.outbox.read() == []


def test_entries_added_during_the_request_survive_the_cleanup(env):
    env.outbox.append({"ts": "t", "level": "ERROR", "message": "first"})

    def handler(request):
        env.calls.append(request)
        env.outbox.append({"ts": "t", "level": "ERROR", "message": "during"})
        return httpx.Response(200, json={"saved": 1})

    sender = env.sender()
    sender._client_factory = lambda endpoint: ReceiverClient(endpoint, transport=httpx.MockTransport(handler))
    sender.run_once()
    assert [e["message"] for e in env.outbox.read()] == ["during"]


def test_empty_outbox_makes_no_log_request(env):
    env.sender().run_once()
    assert env.calls == []


def test_many_entries_are_chunked(env):
    for i in range(650):
        env.outbox.append({"ts": "t", "level": "ERROR", "message": f"m{i}"})
    env.sender().run_once()
    assert [len(b["entries"]) for b in env.bodies("/v1/logs")] == [200, 200, 200, 50]


# ── 미리보기·상태·삭제 ─────────────────────────────────────────────


def test_preview_shows_what_would_be_sent_without_any_network_call_and_even_with_consent_off(env):
    env.configure(labels=False, logs=False)
    env.add_clip("c1", labelNote="메모 원문")
    env.outbox.append({"ts": "t", "level": "ERROR", "message": "테스트닉 님"})
    preview = env.sender().preview()
    assert env.calls == [] and env.factory_calls == 0
    assert preview["labels"]["count"] == 1 and preview["labels"]["items"][0]["labelNote"] == "메모 원문"
    assert preview["logs"]["count"] == 1 and "테스트닉" not in json.dumps(preview["logs"], ensure_ascii=False)
    assert preview["logs"]["env"]["appVersion"] == "0.1.1"


def test_preview_lists_only_what_is_still_unsent(env):
    env.add_clip("c1")
    sender = env.sender()
    sender.run_once()
    env.add_clip("c2")
    assert sender.preview()["labels"]["count"] == 1


def test_status_reports_pending_counts_and_last_success(env):
    env.add_clip("c1")
    env.outbox.append({"ts": "t", "level": "ERROR", "message": "m"})
    sender = env.sender()
    before = sender.status()
    assert before["pendingLabels"] == 1 and before["pendingLogs"] == 1 and before["lastLabelsSentAt"] is None
    assert before["sendLabels"] is True and before["endpointConfigured"] is True and before["canSendInThisMode"] is True
    sender.run_once()
    after = sender.status()
    assert after["pendingLabels"] == 0 and after["pendingLogs"] == 0 and after["lastLabelsSentAt"] == env.clock.now


def test_status_reflects_dev_mode_block(env):
    assert env.sender(frozen=False).status()["canSendInThisMode"] is False


def test_delete_remote_deletes_by_full_install_id_then_resets_local_state_and_turns_sending_off(env):
    env.add_clip("c1")
    env.outbox.append({"ts": "t", "level": "ERROR", "message": "m"})
    sender = env.sender()
    sender.run_once()
    install_id = load_config(env.config_path).telemetry.install_id
    env.calls.clear()
    env.outbox.append({"ts": "t", "level": "ERROR", "message": "later"})
    result = sender.delete_remote()
    assert result["ok"] is True
    (call,) = env.calls
    assert call.method == "DELETE" and call.url.path == f"/v1/installs/{install_id}"
    cfg = load_config(env.config_path)
    assert cfg.telemetry.send_labels is False and cfg.telemetry.send_logs is False
    assert env.outbox.read() == [] and sender.status()["pendingLabels"] == 1


def test_delete_remote_failure_changes_nothing_locally(env):
    env.add_clip("c1")
    sender = env.sender()
    sender.run_once()
    env.respond(500)
    result = sender.delete_remote()
    assert result["ok"] is False
    cfg = load_config(env.config_path)
    assert cfg.telemetry.send_labels is True and sender.status()["pendingLabels"] == 0


def test_delete_remote_works_even_when_sending_is_off(env):
    env.configure(labels=False, logs=False)
    assert env.sender().delete_remote()["ok"] is True
    assert env.calls[0].method == "DELETE"


def test_delete_remote_without_a_token_reports_not_configured(env, monkeypatch):
    monkeypatch.delenv("LUMIA_RECEIVER_TOKEN", raising=False)
    monkeypatch.setattr("lumia_briefing_room.telemetry.endpoint.bundled_endpoint", lambda: {})
    env.configure(token="")
    result = env.sender().delete_remote()
    assert result["ok"] is False and result["reason"] == "no-endpoint" and env.calls == []


# ── 스케줄러 ────────────────────────────────────────────────────────


def test_run_forever_survives_exceptions_and_stops_on_event(env):
    sender = env.sender()
    stop = threading.Event()
    runs = []

    def flaky(force=False):
        runs.append(1)
        if len(runs) == 1:
            raise RuntimeError("boom")
        if len(runs) >= 3:
            stop.set()

    sender.run_once = flaky
    sender.run_forever(stop, interval_sec=0, initial_delay_sec=0)
    assert len(runs) >= 3


def test_run_forever_waits_the_initial_delay_before_the_first_send(env):
    sender = env.sender()
    waits = []
    stop = threading.Event()

    def fake_wait(seconds):
        waits.append(seconds)
        stop.set()
        return True

    sender.run_once = lambda force=False: waits.append("ran")
    sender.run_forever(stop, interval_sec=900, initial_delay_sec=60, wait=fake_wait)
    assert waits == [60]
