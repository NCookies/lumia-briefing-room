import json

import httpx
import pytest

from lumia_briefing_room.telemetry.client import Endpoint, ReceiverClient

ENDPOINT = Endpoint(url="https://receiver.example", token="tok-123")
INSTALL = "3f2b8c1e-5a4d-4e6f-9b7a-1c2d3e4f5a6b"


def client_for(handler):
    return ReceiverClient(ENDPOINT, transport=httpx.MockTransport(handler))


def respond(status, body=None, headers=None):
    return lambda request: httpx.Response(status, json=body if body is not None else {}, headers=headers)


def test_success_returns_ok_with_the_parsed_body():
    result = client_for(respond(200, {"saved": 3})).post("/v1/labels", {"a": 1})
    assert result.outcome == "ok" and result.status == 200 and result.data == {"saved": 3}


def test_sends_the_token_and_a_json_body_to_the_right_url():
    seen = {}

    def handler(request):
        seen["url"], seen["token"] = str(request.url), request.headers["x-api-token"]
        seen["type"], seen["body"] = request.headers["content-type"], json.loads(request.content)
        return httpx.Response(200, json={"saved": 1})

    client_for(handler).post("/v1/labels", {"installId": INSTALL, "labelNote": "한글 메모"})
    assert seen["url"] == "https://receiver.example/v1/labels" and seen["token"] == "tok-123"
    assert seen["type"].startswith("application/json") and seen["body"]["labelNote"] == "한글 메모"


def test_base_url_trailing_slash_is_tolerated():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={})

    ReceiverClient(Endpoint("https://receiver.example/", "t"), transport=httpx.MockTransport(handler)).post("/v1/logs", {})
    assert seen["url"] == "https://receiver.example/v1/logs"


@pytest.mark.parametrize("status", [400, 413, 422])
def test_client_errors_that_will_never_succeed_are_dropped(status):
    result = client_for(respond(status, {"detail": "x"})).post("/v1/labels", {})
    assert result.outcome == "drop" and result.status == status


@pytest.mark.parametrize("status", [401, 403, 404, 500, 502, 503])
def test_auth_and_server_errors_are_retried_later(status):
    result = client_for(respond(status)).post("/v1/labels", {})
    assert result.outcome == "retry" and result.status == status


def test_rate_limited_is_retried_and_reports_retry_after():
    result = client_for(respond(429, {}, {"Retry-After": "3600"})).post("/v1/labels", {})
    assert result.outcome == "retry" and result.status == 429 and result.retry_after == 3600


def test_bad_retry_after_is_ignored():
    result = client_for(respond(429, {}, {"Retry-After": "soon"})).post("/v1/labels", {})
    assert result.outcome == "retry" and result.retry_after is None


@pytest.mark.parametrize(
    "error",
    [httpx.ConnectTimeout("t"), httpx.ReadTimeout("t"), httpx.ConnectError("refused"), httpx.RemoteProtocolError("x"),
     OSError("network down")],
)
def test_network_failures_never_raise_and_are_retried_later(error):
    def handler(request):
        raise error

    result = client_for(handler).post("/v1/labels", {})
    assert result.outcome == "retry" and result.status is None


def test_non_json_response_body_is_tolerated():
    result = client_for(lambda r: httpx.Response(200, content=b"<html>proxy</html>")).post("/v1/logs", {})
    assert result.outcome == "ok" and result.data is None


def test_unserializable_payload_is_dropped_instead_of_crashing():
    result = client_for(respond(200)).post("/v1/logs", {"x": object()})
    assert result.outcome == "drop" and result.status is None


def test_delete_install_uses_the_delete_verb_and_the_full_install_id():
    seen = {}

    def handler(request):
        seen["method"], seen["path"] = request.method, request.url.path
        return httpx.Response(200, json={"deleted": True})

    result = client_for(handler).delete_install(INSTALL)
    assert seen == {"method": "DELETE", "path": f"/v1/installs/{INSTALL}"}
    assert result.outcome == "ok" and result.data == {"deleted": True}


def test_delete_install_failure_is_reported_not_raised():
    def handler(request):
        raise httpx.ConnectError("refused")

    assert client_for(handler).delete_install(INSTALL).outcome == "retry"
