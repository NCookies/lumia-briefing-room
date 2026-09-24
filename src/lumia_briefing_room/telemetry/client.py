"""수신 서버 HTTP 클라이언트. 어떤 실패도 예외로 내보내지 않고 결과 분류(`SendResult.outcome`)로만 돌려준다.

- `ok`    성공
- `drop`  다시 보내도 같은 결과일 요청(400·413·422, 직렬화 불가) — 호출자는 그 묶음을 버린다
- `retry` 나중에 다시 시도할 만한 실패(401·403·404·429·5xx, 타임아웃·연결 거부 등)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger("lumia_briefing_room.telemetry.client")

TIMEOUT_SEC = 10.0
DROP_STATUSES = {400, 413, 422}


@dataclass(frozen=True)
class Endpoint:
    url: str
    token: str


@dataclass(frozen=True)
class SendResult:
    outcome: str
    status: int | None = None
    retry_after: float | None = None
    data: dict | None = None


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return float(response.headers.get("retry-after", ""))
    except ValueError:
        return None


def _data(response: httpx.Response) -> dict | None:
    try:
        value = response.json()
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _classify(response: httpx.Response) -> SendResult:
    status = response.status_code
    if 200 <= status < 300:
        return SendResult("ok", status, data=_data(response))
    if status in DROP_STATUSES:
        return SendResult("drop", status, data=_data(response))
    return SendResult("retry", status, retry_after=_retry_after(response))


class ReceiverClient:
    def __init__(self, endpoint: Endpoint, *, transport: httpx.BaseTransport | None = None, timeout: float = TIMEOUT_SEC):
        self.endpoint = endpoint
        self._client = httpx.Client(
            base_url=endpoint.url.rstrip("/"),
            headers={"X-Api-Token": endpoint.token, "User-Agent": "lumia-briefing-room"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs) -> SendResult:
        try:
            return _classify(self._client.request(method, path, **kwargs))
        except Exception as exc:
            log.info("서버에 연결하지 못했다 (%s %s): %s", method, path, type(exc).__name__)
            return SendResult("retry")

    def post(self, path: str, payload: dict) -> SendResult:
        try:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError):
            log.warning("직렬화할 수 없는 전송 내용을 버린다 (%s)", path)
            return SendResult("drop")
        return self._request("POST", path, content=body, headers={"Content-Type": "application/json"})

    def delete_install(self, install_id: str) -> SendResult:
        return self._request("DELETE", f"/v1/installs/{install_id}")
