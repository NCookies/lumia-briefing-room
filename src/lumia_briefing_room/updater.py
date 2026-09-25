"""새 버전 확인과 설치기 실행. (plan-deploy.md D9, SPEC §7.11)

원칙
- 자동 확인은 `update.check` 가 켜져 있을 때만, 시작 시와 하루 1회 GitHub Releases API 로 한다. 꺼져 있으면 네트워크를 아예 쓰지 않는다.
- 수동 확인·설치(`check()`·`start_install()`)는 사용자가 직접 누른 동작이라 `update.check` 값과 무관하게 동작한다.
- 앱이 실행 중인 파일을 직접 교체하지 않는다. 설치기를 받아 SHA-256 을 확인한 뒤 실행하고, 설치기가 앱을 닫고 덮어쓴다.
- 체크섬 파일(`<설치기>.sha256`)이 없거나 값이 다르면 설치기를 실행하지 않는다. 서명이 없는 배포라 이 검증이 업데이트 경로의 유일한 무결성 확인이다.
- 어떤 실패도 예외로 내보내지 않고 상태(`error`/`failed`)로만 알린다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from lumia_briefing_room import __version__, paths, procs
from lumia_briefing_room.config import Config, _default_local_appdata, load_config, resolve_config_path

log = logging.getLogger("lumia_briefing_room.updater")

REPO = "NCookies/lumia-briefing-room"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
CHECK_INTERVAL = 24 * 3600.0
RETRY_INTERVAL = 3600.0
LOOP_TICK = 300.0
API_TIMEOUT = 10.0
DOWNLOAD_TIMEOUT = httpx.Timeout(10.0, read=60.0)
CHECKSUM_MAX_BYTES = 4096
_VERSION = re.compile(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
_SHA256_LINE = re.compile(r"^([0-9a-fA-F]{64}) [ *](.+)$")


class UpdateError(Exception):
    pass


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = _VERSION.fullmatch(str(text).strip())
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(latest: str, current: str) -> bool:
    latest_v, current_v = parse_version(latest), parse_version(current)
    return latest_v is not None and current_v is not None and latest_v > current_v


def installer_command(path) -> list[str]:
    """설치기를 조용히 실행한다(마법사 페이지 없이 진행 표시만). 설치가 끝나면 앱을 다시 띄운다(/RELAUNCH=1, installer/lumia.iss)."""
    return [str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH=1"]


def launch_installer(path) -> None:
    command = installer_command(path)
    try:
        subprocess.Popen(command, creationflags=procs.installer_flags(), close_fds=True)
    except OSError:
        # 작업 개체가 분리를 허용하지 않는 환경이면 분리 없이 다시 시도한다.
        subprocess.Popen(command, creationflags=procs.installer_flags() & ~procs.CREATE_BREAKAWAY_FROM_JOB, close_fds=True)


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    installer_name: str
    installer_url: str
    sha256_url: str
    notes: str = ""
    page_url: str = ""

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "installerName": self.installer_name,
            "installerUrl": self.installer_url,
            "sha256Url": self.sha256_url,
            "notes": self.notes,
            "pageUrl": self.page_url,
        }

    @classmethod
    def from_dict(cls, data) -> ReleaseInfo | None:
        try:
            return cls(
                version=str(data["version"]),
                installer_name=str(data["installerName"]),
                installer_url=str(data["installerUrl"]),
                sha256_url=str(data["sha256Url"]),
                notes=str(data.get("notes", "")),
                page_url=str(data.get("pageUrl", "")),
            )
        except (KeyError, TypeError, AttributeError):
            return None


def parse_release(payload, *, download_prefix: str) -> ReleaseInfo | None:
    """API 응답에서 설치기 정보를 뽑는다. 초안·사전 릴리스면 None, 설치기나 체크섬이 없거나 주소가 저장소 릴리스가 아니면 UpdateError."""
    if not isinstance(payload, dict):
        raise UpdateError("릴리스 정보 형식이 올바르지 않습니다")
    if payload.get("draft") or payload.get("prerelease"):
        return None
    version = str(payload.get("tag_name", "")).strip()
    if parse_version(version) is None:
        raise UpdateError(f"릴리스 태그를 읽을 수 없습니다: {version!r}")
    version = version.lstrip("v")
    assets = {
        str(a.get("name", "")): str(a.get("browser_download_url", ""))
        for a in payload.get("assets") or []
        if isinstance(a, dict)
    }
    installer_name = next((n for n in assets if n.endswith("-setup.exe")), None)
    if installer_name is None:
        raise UpdateError("릴리스에 설치기가 없습니다")
    sha256_url = assets.get(installer_name + ".sha256")
    if not sha256_url:
        raise UpdateError("릴리스에 체크섬(.sha256) 파일이 없어 설치기를 검증할 수 없습니다")
    for url in (assets[installer_name], sha256_url):
        if not url.startswith(download_prefix):
            raise UpdateError("릴리스 파일 주소가 이 저장소의 릴리스가 아닙니다")
    return ReleaseInfo(
        version=version,
        installer_name=installer_name,
        installer_url=assets[installer_name],
        sha256_url=sha256_url,
        notes=str(payload.get("body") or ""),
        page_url=str(payload.get("html_url") or ""),
    )


def parse_checksum(text: str, installer_name: str) -> str:
    for line in text.splitlines():
        match = _SHA256_LINE.match(line.strip())
        if match:
            if match.group(2) != installer_name:
                raise UpdateError("체크섬 파일이 이 설치기의 것이 아닙니다")
            return match.group(1).lower()
    raise UpdateError("체크섬 파일에서 SHA-256 값을 읽을 수 없습니다")


def default_state_path() -> Path:
    return _default_local_appdata() / "LumiaBriefingRoom" / "update_state.json"


def default_download_dir() -> Path:
    return _default_local_appdata() / "LumiaBriefingRoom" / "updates"


_IDLE_INSTALL = {"state": "idle", "downloaded": 0, "total": 0, "error": ""}


class Updater:
    def __init__(
        self,
        *,
        config_path: Path | None = None,
        state_path: Path | None = None,
        download_dir: Path | None = None,
        current_version: str = __version__,
        api_url: str = API_URL,
        download_prefix: str = DOWNLOAD_PREFIX,
        clock: Callable[[], float] = time.time,
        launcher: Callable[[Path], None] | None = None,
        notify: Callable[[dict], None] | None = None,
        on_launched: Callable[[], None] | None = None,
        frozen: bool | None = None,
    ):
        self.config_path = config_path
        self.state_path = Path(state_path) if state_path else default_state_path()
        self.download_dir = Path(download_dir) if download_dir else default_download_dir()
        self.current = current_version
        self.api_url = api_url
        self.download_prefix = download_prefix
        self.clock = clock
        self._launcher = launcher
        self._notify = notify
        self._on_launched = on_launched
        self.frozen = paths.is_frozen() if frozen is None else frozen
        self._lock = threading.RLock()
        self._install = dict(_IDLE_INSTALL)
        self._install_thread: threading.Thread | None = None

    # ── 상태 파일 ────────────────────────────────────────────────────

    def _load_state(self) -> dict:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_state(self, **changes) -> None:
        with self._lock:
            state = self._load_state() | changes
            try:
                self.state_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.state_path.with_suffix(".tmp")
                tmp.write_text(json.dumps(state), encoding="utf-8")
                tmp.replace(self.state_path)
            except OSError:
                log.info("업데이트 상태를 저장하지 못했다", exc_info=False)

    def _cfg(self) -> Config:
        return load_config(resolve_config_path(self.config_path))

    # ── 확인 ─────────────────────────────────────────────────────────

    def _fetch_latest(self) -> ReleaseInfo | None:
        try:
            with httpx.Client(timeout=API_TIMEOUT, headers={
                "Accept": "application/vnd.github+json", "User-Agent": "lumia-briefing-room",
            }) as client:
                response = client.get(self.api_url)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise UpdateError(f"릴리스 정보를 받지 못했습니다 (HTTP {exc.response.status_code})") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise UpdateError("업데이트 서버에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요") from exc
        return parse_release(payload, download_prefix=self.download_prefix)

    def check(self) -> dict:
        """지금 확인한다(수동 확인). 결과는 `state` 가 available/latest/error 인 dict, 예외는 내지 않는다."""
        try:
            release = self._fetch_latest()
        except UpdateError as exc:
            log.info("업데이트 확인 실패: %s", exc)
            self._save_state(nextAttempt=self.clock() + RETRY_INTERVAL)
            return {"state": "error", "current": self.current, "error": str(exc)}
        except Exception:
            log.exception("업데이트 확인 중 예상하지 못한 오류")
            self._save_state(nextAttempt=self.clock() + RETRY_INTERVAL)
            return {"state": "error", "current": self.current, "error": "업데이트를 확인하지 못했습니다"}
        now = self.clock()
        if release is None or not is_newer(release.version, self.current):
            self._save_state(lastCheck=now, nextAttempt=now + CHECK_INTERVAL, latest=None)
            return {"state": "latest", "current": self.current}
        self._save_state(lastCheck=now, nextAttempt=now + CHECK_INTERVAL, latest=release.to_dict())
        return {"state": "available", "current": self.current, "release": release.to_dict()}

    def maybe_auto_check(self) -> dict | None:
        """`update.check` 가 켜져 있고 확인할 때가 됐으면 확인한다. 아니면 네트워크를 쓰지 않고 None."""
        if not self._cfg().update.check:
            return None
        if self.clock() < float(self._load_state().get("nextAttempt") or 0.0):
            return None
        result = self.check()
        if result["state"] == "available":
            self._notify_once(result["release"])
        return result

    def _notify_once(self, release: dict) -> None:
        if self._notify is None or self._load_state().get("notified") == release["version"]:
            return
        try:
            self._notify(release)
        except Exception:
            log.info("새 버전 알림을 띄우지 못했다", exc_info=False)
            return
        self._save_state(notified=release["version"])

    def run_forever(self, stop: threading.Event, tick: float = LOOP_TICK) -> None:
        while not stop.is_set():
            try:
                self.maybe_auto_check()
            except Exception:
                log.exception("자동 업데이트 확인 중 예상하지 못한 오류")
            if stop.wait(tick):
                return

    def status(self) -> dict:
        state = self._load_state()
        enabled = self._cfg().update.check
        release = ReleaseInfo.from_dict(state["latest"]) if state.get("latest") else None
        available = release if enabled and release and is_newer(release.version, self.current) else None
        with self._lock:
            install = dict(self._install)
        return {
            "enabled": enabled,
            "current": self.current,
            "lastChecked": state.get("lastCheck"),
            "available": available.to_dict() if available else None,
            "install": install,
        }

    # ── 설치 ─────────────────────────────────────────────────────────

    def _set_install(self, **changes) -> None:
        with self._lock:
            self._install.update(changes)

    def start_install(self) -> bool:
        """받아서 검증하고 설치기를 실행하는 작업을 백그라운드로 시작한다. 이미 진행 중이면 False."""
        with self._lock:
            if self._install_thread is not None and self._install_thread.is_alive():
                return False
            self._install = dict(_IDLE_INSTALL, state="downloading")
            self._install_thread = threading.Thread(target=self._install_worker, daemon=True, name="update-install")
            self._install_thread.start()
            return True

    def wait_install(self, timeout: float | None = None) -> None:
        thread = self._install_thread
        if thread is not None:
            thread.join(timeout)

    def install_sync(self) -> None:
        self._set_install(state="downloading", downloaded=0, total=0, error="")
        self._install_worker()

    def _install_worker(self) -> None:
        try:
            self._do_install()
        except UpdateError as exc:
            log.warning("업데이트 설치 실패: %s", exc)
            self._set_install(state="failed", error=str(exc))
        except Exception:
            log.exception("업데이트 설치 중 예상하지 못한 오류")
            self._set_install(state="failed", error="업데이트를 설치하지 못했습니다")

    def _do_install(self) -> None:
        if self._launcher is None and not self.frozen:
            raise UpdateError("개발 모드에서는 설치기를 실행하지 않습니다. 설치된 앱에서 업데이트해 주세요")
        result = self.check()
        if result["state"] == "error":
            raise UpdateError(result["error"])
        if result["state"] != "available":
            raise UpdateError("이미 최신 버전입니다")
        release = ReleaseInfo.from_dict(result["release"])
        path = self._download_verified(release)
        self._set_install(state="launching")
        try:
            (self._launcher or launch_installer)(path)
        except OSError as exc:
            raise UpdateError(f"설치기를 실행하지 못했습니다: {exc}") from exc
        self._set_install(state="launched")
        if self._on_launched is not None:
            self._on_launched()

    def _download_verified(self, release: ReleaseInfo) -> Path:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        for old in self.download_dir.glob("*"):
            try:
                old.unlink()
            except OSError:
                pass
        target = self.download_dir / release.installer_name
        partial = target.with_name(target.name + ".part")
        try:
            with httpx.Client(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True,
                              headers={"User-Agent": "lumia-briefing-room"}) as client:
                expected = self._fetch_checksum(client, release)
                digest = hashlib.sha256()
                with client.stream("GET", release.installer_url) as response:
                    response.raise_for_status()
                    self._set_install(state="downloading", total=int(response.headers.get("content-length") or 0))
                    downloaded = 0
                    with partial.open("wb") as out:
                        for chunk in response.iter_bytes(1 << 20):
                            out.write(chunk)
                            digest.update(chunk)
                            downloaded += len(chunk)
                            self._set_install(downloaded=downloaded)
            self._set_install(state="verifying")
            if downloaded == 0 or digest.hexdigest() != expected:
                raise UpdateError("받은 설치기의 SHA-256 이 릴리스의 체크섬과 달라 실행하지 않았습니다")
            partial.replace(target)
            return target
        except httpx.HTTPStatusError as exc:
            raise UpdateError(f"설치기를 받지 못했습니다 (HTTP {exc.response.status_code})") from exc
        except httpx.HTTPError as exc:
            raise UpdateError("설치기를 받는 중 연결이 끊겼습니다") from exc
        finally:
            partial.unlink(missing_ok=True)

    def _fetch_checksum(self, client: httpx.Client, release: ReleaseInfo) -> str:
        try:
            response = client.get(release.sha256_url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpdateError("체크섬 파일을 받지 못했습니다") from exc
        if len(response.content) > CHECKSUM_MAX_BYTES:
            raise UpdateError("체크섬 파일이 너무 큽니다")
        return parse_checksum(response.text, release.installer_name)

