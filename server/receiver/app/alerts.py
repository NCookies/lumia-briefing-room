"""Discord 웹훅 알림. 웹훅 URL 은 비밀 값이라 환경변수(DISCORD_WEBHOOK_URL)로만 받고 저장소에 넣지 않는다.

알림이 실패해도 요청 처리는 영향받지 않는다. 회전하는 IP 로 알림이 쏟아지지 않도록 시간당 개수를 제한한다.
"""

import ipaddress
import json
import logging
import threading
import time
import urllib.request
from typing import Callable

log = logging.getLogger("receiver.alerts")


def mask_ip(ip: str) -> str:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "?"
    if addr.version == 4:
        a, b, *_ = str(addr).split(".")
        return f"{a}.{b}.*.*"
    first, second, *_ = addr.exploded.split(":")
    return f"{first.lstrip('0') or '0'}:{second.lstrip('0') or '0'}:*"


def discord_sender(webhook_url: str, timeout: float = 5.0) -> Callable[[str], None]:
    def send(text: str) -> None:
        request = urllib.request.Request(
            webhook_url,
            data=json.dumps({"content": text}).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "lumia-receiver/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout):
            pass

    return send


def _in_thread(func, *args) -> None:
    threading.Thread(target=func, args=args, daemon=True).start()


class Alerter:
    def __init__(
        self,
        send: Callable[[str], None] | None,
        max_per_hour: int = 10,
        clock: Callable[[], float] = time.monotonic,
        run: Callable = _in_thread,
    ):
        self.send = send
        self.max_per_hour = max_per_hour
        self.clock = clock
        self.run = run
        self._sent: list[float] = []

    def notify(self, text: str) -> None:
        if self.send is None:
            return
        now = self.clock()
        self._sent = [t for t in self._sent if t > now - 3600]
        if len(self._sent) >= self.max_per_hour:
            return
        self._sent.append(now)
        self.run(self._safe_send, text)

    def _safe_send(self, text: str) -> None:
        try:
            self.send(text)
        except Exception:
            log.warning("alert delivery failed", exc_info=False)
