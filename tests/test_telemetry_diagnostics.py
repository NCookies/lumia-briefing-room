import json
import re

import httpx
import pytest

from lumia_briefing_room.config import load_config
from lumia_briefing_room.telemetry.client import ReceiverClient
from lumia_briefing_room.telemetry.outbox import Outbox, OutboxHandler
from lumia_briefing_room.telemetry.payload import display_id
from test_telemetry_sender import Env, validate  # noqa: E402


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def add_error(env, message, **extra):
    entry = {"ts": "2026-09-25T00:00:00Z", "level": "ERROR", "logger": "lumia_briefing_room.x", "message": message, **extra}
    env.recent.append(entry)
    env.outbox.append(entry)


# ── 최근 오류 기록(정기 전송으로 지워지지 않는다) ───────────────────


def test_handler_writes_both_the_outbox_and_the_recent_ring(tmp_path):
    import logging

    outbox, recent = Outbox(tmp_path / "o.jsonl"), Outbox(tmp_path / "r.jsonl")
    logger = logging.getLogger("lumia_briefing_room.diag.a")
    logger.handlers, logger.propagate = [], False
    logger.addHandler(OutboxHandler(outbox, recent=recent))
    logger.error("boom")
    assert [e["message"] for e in outbox.read()] == ["boom"] and [e["message"] for e in recent.read()] == ["boom"]
    outbox.clear()
    assert [e["message"] for e in recent.read()] == ["boom"]


def test_recent_ring_is_capped_at_one_megabyte_by_default():
    from lumia_briefing_room.telemetry import outbox as ob

    assert ob.RECENT_MAX_BYTES == 1024 * 1024


# ── 미리보기 ────────────────────────────────────────────────────────


def test_preview_is_scrubbed_needs_no_network_and_works_with_every_consent_off(env):
    env.configure(labels=False, logs=False)
    add_error(env, r"열 수 없다 C:\Users\tester\a.mp4 테스트닉", exceptionType="OSError",
              stack='File "C:\\Users\\tester\\x\\lumia_briefing_room\\a.py", line 3, in f\nOSError: x')
    preview = env.sender().diagnostics_preview()
    blob = json.dumps(preview, ensure_ascii=False)
    assert env.calls == [] and env.factory_calls == 0
    assert "tester" not in blob and "테스트닉" not in blob and "Users" not in blob
    assert preview["count"] == 1 and preview["env"]["appVersion"] == "0.1.1"
    assert preview["displayId"].startswith("LUMIA-") and preview["canSend"] is True


def test_preview_bundle_matches_the_diagnostic_contract(env):
    add_error(env, "boom")
    sender = env.sender()
    bundle = sender.diagnostic_bundle()
    assert validate("DiagnosticBundle", bundle) == []
    assert bundle["displayId"] == display_id(bundle["installId"]) and bundle["mode"] == "release"


def test_only_the_latest_100_entries_are_included_oldest_dropped(env):
    for i in range(130):
        add_error(env, f"m{i:03d}")
    preview = env.sender().diagnostics_preview()
    messages = [e["message"] for e in preview["items"]]
    assert preview["count"] == 100 and messages[0] == "m030" and messages[-1] == "m129"


def test_falls_back_to_the_outbox_when_no_recent_ring_exists_yet(env):
    env.outbox.append({"ts": "t", "level": "ERROR", "message": "old"})
    assert env.sender().diagnostics_preview()["count"] == 1


def test_preview_with_no_errors_still_shows_the_environment(env):
    preview = env.sender().diagnostics_preview()
    assert preview["count"] == 0 and preview["env"]["appVersion"]


def test_preview_says_when_this_build_cannot_send(env, monkeypatch):
    monkeypatch.delenv("LUMIA_RECEIVER_TOKEN", raising=False)
    monkeypatch.setattr("lumia_briefing_room.telemetry.endpoint.bundled_endpoint", lambda: {})
    env.configure(token="")
    preview = env.sender().diagnostics_preview()
    assert preview["endpointConfigured"] is False and preview["canSend"] is False


def test_dev_mode_preview_says_it_cannot_send(env):
    assert env.sender(frozen=False).diagnostics_preview()["canSend"] is False


# ── 전송 ────────────────────────────────────────────────────────────


def test_send_posts_the_bundle_and_returns_the_receipt_id(env):
    add_error(env, "boom")
    result = env.sender().send_diagnostics()
    assert result == {"ok": True, "receiptId": "R-20260925-K7M3QX", "saved": 1}
    (call,) = env.calls
    assert call.method == "POST" and call.url.path == "/v1/diagnostics"
    assert validate("DiagnosticBundle", json.loads(call.content)) == []


def test_send_works_even_when_both_regular_consents_are_off(env):
    env.configure(labels=False, logs=False)
    add_error(env, "boom")
    assert env.sender().send_diagnostics()["ok"] is True
    assert len(env.calls) == 1


def test_sending_does_not_touch_the_regular_queues_or_turn_anything_on(env):
    env.configure(labels=False, logs=False)
    add_error(env, "boom")
    env.sender().send_diagnostics()
    cfg = load_config(env.config_path)
    assert cfg.telemetry.send_logs is False and cfg.telemetry.send_labels is False
    assert len(env.outbox.read()) == 1 and len(env.recent.read()) == 1


def test_each_send_is_a_separate_one_shot_request(env):
    sender = env.sender()
    sender.send_diagnostics()
    sender.send_diagnostics()
    assert len(env.calls) == 2


def test_the_receipt_is_remembered_and_shown_in_status(env):
    sender = env.sender()
    assert sender.status()["lastDiagnosticReceipt"] is None
    sender.send_diagnostics()
    status = sender.status()
    assert status["lastDiagnosticReceipt"] == "R-20260925-K7M3QX" and status["lastDiagnosticAt"] == env.clock.now


def test_the_bundle_never_contains_the_full_install_id_in_a_display_field_or_private_text(env):
    add_error(env, r"C:\Users\tester\Videos\테스트닉\a.mp4")
    result_body = None
    env.sender().send_diagnostics()
    result_body = json.loads(env.calls[0].content)
    blob = json.dumps(result_body, ensure_ascii=False)
    assert "tester" not in blob and "테스트닉" not in blob


@pytest.mark.parametrize("failure,reason", [(500, "server"), (401, "server"), (httpx.ConnectError("x"), "network"),
                                            (httpx.ReadTimeout("x"), "network")])
def test_failures_are_reported_not_raised_and_nothing_is_recorded(env, failure, reason):
    env.respond(failure)
    result = env.sender().send_diagnostics()
    assert result["ok"] is False and result["reason"] == reason
    assert env.sender().status()["lastDiagnosticReceipt"] is None


@pytest.mark.parametrize("status", [413, 422])
def test_rejected_bundles_say_so(env, status):
    env.respond(status)
    assert env.sender().send_diagnostics()["reason"] == "rejected"


def test_no_token_means_a_clear_reason_and_no_network(env, monkeypatch):
    monkeypatch.delenv("LUMIA_RECEIVER_TOKEN", raising=False)
    monkeypatch.setattr("lumia_briefing_room.telemetry.endpoint.bundled_endpoint", lambda: {})
    env.configure(token="")
    result = env.sender().send_diagnostics()
    assert result["reason"] == "no-endpoint" and env.calls == []


def test_dev_mode_is_blocked_unless_allowed(env):
    result = env.sender(frozen=False).send_diagnostics()
    assert result["reason"] == "dev-blocked" and env.calls == []
    env.configure(allow_dev=True)
    assert env.sender(frozen=False).send_diagnostics()["ok"] is True
    assert json.loads(env.calls[0].content)["mode"] == "dev"


def test_a_malformed_receipt_from_the_server_is_not_shown_as_a_number(env):
    sender = env.sender()
    sender._client_factory = lambda endpoint: ReceiverClient(
        endpoint, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"receiptId": "<script>", "saved": 1})))
    result = sender.send_diagnostics()
    assert result["ok"] is True and result["receiptId"] is None


def test_deleting_my_data_forgets_the_remembered_receipt(env):
    sender = env.sender()
    sender.send_diagnostics()
    sender.delete_remote()
    assert sender.status()["lastDiagnosticReceipt"] is None


def test_receipt_pattern_matches_what_the_server_issues():
    assert re.fullmatch(r"R-\d{8}-[A-Z2-9]{6}", "R-20260925-K7M3QX")
