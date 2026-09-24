"""라벨·오류 로그 전송 스케줄러. (plan-deploy.md D10)

원칙
- 동의(`telemetry.sendLabels`/`sendLogs`)가 꺼져 있으면 네트워크를 아예 쓰지 않는다(클라이언트도 만들지 않는다).
- 개발 모드는 `telemetry.allowDevSend` 를 켠 경우에만 보내고, 그때는 `mode=dev` 로 보내 서버가 운영 데이터와 분리해 둔다.
- 종류별로 하루 한 번 묶어서 보낸다. 실패하면 15분부터 두 배씩(최대 6시간) 늦춰 다시 시도하고, 서버가 준 Retry-After 가 길면 그것을 따른다.
- 서버가 절대 받지 않을 묶음(413·422)은 버리고 다음 날 같은 것을 또 보내지 않는다. 라벨은 내용이 바뀌어야 다시 보낸다.
- 어떤 서버 오류도 앱을 멈추지 않는다.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from lumia_briefing_room import __version__, paths
from lumia_briefing_room.appmode import resolve_mode
from lumia_briefing_room.config import Config, load_config, resolve_config_path, save_config
from lumia_briefing_room.telemetry.client import Endpoint, ReceiverClient, SendResult
from lumia_briefing_room.telemetry.collect import collect_labels
from lumia_briefing_room.telemetry.endpoint import load_endpoint
from lumia_briefing_room.telemetry.environment import collect_environment
from lumia_briefing_room.telemetry.outbox import Outbox, default_outbox_path
from lumia_briefing_room.telemetry.payload import display_id
from lumia_briefing_room.telemetry.scrub import scrub_entry
from lumia_briefing_room.telemetry.state import TelemetryState, default_state_path

log = logging.getLogger("lumia_briefing_room.telemetry.sender")

DAY = 24 * 3600.0
SCHEMA_VERSION = 1
LABEL_BATCH = 200
LOG_BATCH = 200
BACKOFF_FIRST = 15 * 60.0
BACKOFF_MAX = 6 * 3600.0
PREVIEW_LIMIT = 100
_CONFIG_LOCK = threading.RLock()


def backoff_seconds(failures: int) -> float:
    return min(BACKOFF_FIRST * (2 ** max(failures - 1, 0)), BACKOFF_MAX)


def ensure_install_id(config_path: Path | None) -> str:
    """설정 파일에 설치 ID 가 없으면 무작위 UUID 를 만들어 저장한다. 계정·닉네임과 연결하지 않는다."""
    with _CONFIG_LOCK:
        path = resolve_config_path(config_path)
        cfg = load_config(path)
        current = cfg.telemetry.install_id
        try:
            return str(uuid.UUID(current))
        except ValueError:
            pass
        cfg.telemetry.install_id = str(uuid.uuid4())
        save_config(cfg, path)
        return cfg.telemetry.install_id


def _chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _default_usernames() -> list[str]:
    return [os.environ.get("USERNAME", ""), Path.home().name]


class TelemetrySender:
    def __init__(
        self,
        *,
        config_path: Path | None = None,
        state_path: Path | None = None,
        outbox: Outbox | None = None,
        client_factory: Callable[[Endpoint], ReceiverClient] | None = None,
        clock: Callable[[], float] = time.time,
        frozen: bool | None = None,
        collect_env: Callable[[Config], dict] | None = None,
        usernames: list[str] | None = None,
    ):
        self.config_path = config_path
        self.state = TelemetryState(state_path or default_state_path())
        self.outbox = outbox or Outbox(default_outbox_path())
        self._client_factory = client_factory or ReceiverClient
        self.clock = clock
        self.frozen = paths.is_frozen() if frozen is None else frozen
        self._collect_env = collect_env or collect_environment
        self.usernames = _default_usernames() if usernames is None else usernames

    # ── 공통 ─────────────────────────────────────────────────────────

    def _cfg(self) -> Config:
        return load_config(resolve_config_path(self.config_path))

    def _mode(self, cfg: Config) -> str:
        return resolve_mode(cfg.app.mode, frozen=self.frozen)

    def _can_send_in_mode(self, cfg: Config) -> bool:
        return self._mode(cfg) == "release" or cfg.telemetry.allow_dev_send

    def _env(self, cfg: Config) -> dict:
        try:
            return self._collect_env(cfg)
        except Exception:
            log.info("환경 정보를 모으지 못했다", exc_info=False)
            return {"appVersion": __version__, "os": "unknown"}

    def _scrubbed_entries(self, cfg: Config, entries: list[dict]) -> list[dict]:
        return [scrub_entry(e, usernames=self.usernames, nicknames=[cfg.player.nickname]) for e in entries]

    def _pending_labels(self, cfg: Config, install_id: str) -> list[tuple[str, dict, str]]:
        sent = self.state.digests()
        return [item for item in collect_labels(cfg, install_id) if sent.get(item[0]) != item[2]]

    def _fail(self, kind: str, now: float, result: SendResult) -> dict:
        failures = self.state.kind(kind)["failures"] + 1
        wait = max(backoff_seconds(failures), result.retry_after or 0.0)
        self.state.update(kind, failures=failures, nextAttempt=now + wait)
        return {"status": "retry", "httpStatus": result.status}

    def _done(self, kind: str, now: float, *, success: bool) -> None:
        fields = {"failures": 0, "nextAttempt": now + DAY}
        if success:
            fields["lastSuccess"] = now
        self.state.update(kind, **fields)

    # ── 전송 ─────────────────────────────────────────────────────────

    def run_once(self, force: bool = False) -> dict:
        cfg = self._cfg()
        report = {"labels": {"status": "off"}, "logs": {"status": "off"}}
        kinds = [k for k, on in (("labels", cfg.telemetry.send_labels), ("logs", cfg.telemetry.send_logs)) if on]
        if not kinds:
            return report
        if not self._can_send_in_mode(cfg):
            return {k: {"status": "dev-blocked"} for k in report if k in kinds} | {
                k: v for k, v in report.items() if k not in kinds}
        endpoint = load_endpoint(cfg)
        if endpoint is None:
            log.info("서버 토큰이 없어 전송하지 않는다")
            return {k: {"status": "no-endpoint"} for k in report if k in kinds} | {
                k: v for k, v in report.items() if k not in kinds}

        install_id = ensure_install_id(self.config_path)
        mode = self._mode(cfg)
        now = self.clock()
        holder: dict = {}

        def client() -> ReceiverClient:
            if "c" not in holder:
                holder["c"] = self._client_factory(endpoint)
            return holder["c"]

        try:
            if "labels" in kinds:
                report["labels"] = self._send_labels(cfg, client, install_id, mode, now, force)
            if "logs" in kinds:
                report["logs"] = self._send_logs(cfg, client, install_id, mode, now, force)
        finally:
            if "c" in holder:
                try:
                    holder["c"].close()
                except Exception:
                    pass
        return report

    def _send_labels(self, cfg, client, install_id, mode, now, force) -> dict:
        if not force and now < self.state.kind("labels")["nextAttempt"]:
            return {"status": "not-due"}
        pending = self._pending_labels(cfg, install_id)
        if not pending:
            self._done("labels", now, success=False)
            return {"status": "nothing", "count": 0}
        sent = dropped = 0
        for batch in _chunks(pending, LABEL_BATCH):
            payload = {"installId": install_id, "appVersion": __version__, "schemaVersion": SCHEMA_VERSION,
                       "mode": mode, "labels": [label for _, label, _ in batch]}
            result = client().post("/v1/labels", payload)
            if result.outcome == "retry":
                return self._fail("labels", now, result) | {"count": sent}
            if result.outcome == "drop":
                log.warning("서버가 라벨 %d개를 받지 않아 건너뛴다 (HTTP %s)", len(batch), result.status)
                dropped += len(batch)
            else:
                sent += len(batch)
            self.state.remember({key: digest for key, _, digest in batch})
        self._done("labels", now, success=sent > 0)
        return {"status": "sent" if sent else "dropped", "count": sent, "dropped": dropped}

    def _send_logs(self, cfg, client, install_id, mode, now, force) -> dict:
        if not force and now < self.state.kind("logs")["nextAttempt"]:
            return {"status": "not-due"}
        entries = self.outbox.read()
        if not entries:
            self._done("logs", now, success=False)
            return {"status": "nothing", "count": 0}
        env = self._env(cfg)
        sent = dropped = 0
        for chunk in _chunks(entries, LOG_BATCH):
            payload = {"installId": install_id, "schemaVersion": SCHEMA_VERSION, "mode": mode, "env": env,
                       "entries": self._scrubbed_entries(cfg, chunk)}
            result = client().post("/v1/logs", payload)
            if result.outcome == "retry":
                return self._fail("logs", now, result) | {"count": sent}
            if result.outcome == "drop":
                log.warning("서버가 오류 로그 %d개를 받지 않아 버린다 (HTTP %s)", len(chunk), result.status)
                dropped += len(chunk)
            else:
                sent += len(chunk)
            self.outbox.discard_first(len(chunk))
        self._done("logs", now, success=sent > 0)
        return {"status": "sent" if sent else "dropped", "count": sent, "dropped": dropped}

    def run_forever(
        self,
        stop: threading.Event,
        *,
        interval_sec: float = 900.0,
        initial_delay_sec: float = 60.0,
        wait: Callable[[float], bool] | None = None,
    ) -> None:
        """앱이 떠 있는 동안 주기적으로 확인한다. 시작 직후에는 시작 작업과 겹치지 않게 잠시 기다린다."""
        wait = wait or stop.wait
        if wait(initial_delay_sec):
            return
        while not stop.is_set():
            try:
                self.run_once()
            except Exception:
                log.warning("전송 중 예외가 났다 - 다음 주기에 다시 시도한다", exc_info=True)
            if wait(interval_sec):
                break

    # ── 화면용 ───────────────────────────────────────────────────────

    def preview(self) -> dict:
        """보낼 내용(개인정보 제거 후)을 네트워크 없이 보여 준다. 전송이 꺼져 있어도 켜기 전에 볼 수 있다."""
        cfg = self._cfg()
        install_id = ensure_install_id(self.config_path)
        pending = self._pending_labels(cfg, install_id)
        entries = self.outbox.read()
        return {
            "labels": {"count": len(pending), "items": [label for _, label, _ in pending[:PREVIEW_LIMIT]]},
            "logs": {"count": len(entries), "env": self._env(cfg),
                     "items": self._scrubbed_entries(cfg, entries[:PREVIEW_LIMIT])},
            "mode": self._mode(cfg),
        }

    def status(self) -> dict:
        cfg = self._cfg()
        install_id = ensure_install_id(self.config_path)
        return {
            "installId": install_id,
            "displayId": display_id(install_id),
            "sendLabels": cfg.telemetry.send_labels,
            "sendLogs": cfg.telemetry.send_logs,
            "endpointConfigured": load_endpoint(cfg) is not None,
            "mode": self._mode(cfg),
            "canSendInThisMode": self._can_send_in_mode(cfg),
            "pendingLabels": len(self._pending_labels(cfg, install_id)),
            "pendingLogs": len(self.outbox.read()),
            "lastLabelsSentAt": self.state.kind("labels")["lastSuccess"],
            "lastLogsSentAt": self.state.kind("logs")["lastSuccess"],
        }

    def delete_remote(self) -> dict:
        """보낸 데이터 삭제 요청. 사용자가 직접 누른 동작이라 전송 동의와 무관하다.
        성공하면 앞으로 다시 보내지 않도록 전송을 끄고, 로컬 전송 기록을 지운다(다시 켜면 처음부터 다시 보낸다)."""
        cfg = self._cfg()
        endpoint = load_endpoint(cfg)
        if endpoint is None:
            return {"ok": False, "reason": "no-endpoint"}
        install_id = ensure_install_id(self.config_path)
        client = self._client_factory(endpoint)
        try:
            result = client.delete_install(install_id)
        finally:
            try:
                client.close()
            except Exception:
                pass
        if result.outcome != "ok":
            return {"ok": False, "reason": "network" if result.status is None else "server", "httpStatus": result.status}
        with _CONFIG_LOCK:
            path = resolve_config_path(self.config_path)
            fresh = load_config(path)
            fresh.telemetry.send_labels = False
            fresh.telemetry.send_logs = False
            save_config(fresh, path)
        self.state.reset()
        self.outbox.clear()
        return {"ok": True, "deleted": bool((result.data or {}).get("deleted"))}
