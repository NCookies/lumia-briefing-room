"""서버 관리자 API(`GET /v1/admin/labels`)로 라벨을 받아 집계·검색한다. 개발 모드의 관리자 화면과 `tools/pull_labels.py` 가 쓴다. (plan-infra.md §8)

관리자 토큰(`LUMIA_ADMIN_TOKEN`)은 환경변수나 저장소 루트 `.env` 에서만 읽고, 화면·로그·응답에는 내보내지 않는다.
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

import httpx

from lumia_briefing_room import paths
from lumia_briefing_room.envfile import load_env_file, normalize_server_url

TOKEN_ENV = "LUMIA_ADMIN_TOKEN"
URL_ENV = "LUMIA_RECEIVER_URL"
PAGE_LIMIT = 500
ENV_FILE = paths.resource_dir() / ".env"


class AdminError(Exception):
    pass


def read_credentials(env_file: Path | None = None) -> tuple[str, str]:
    """(서버 주소, 관리자 토큰). 환경변수가 `.env` 보다 우선하고, 이 프로세스의 환경변수는 건드리지 않는다."""
    env = dict(os.environ)
    load_env_file(env_file or ENV_FILE, env)
    return normalize_server_url(env.get(URL_ENV, "")), env.get(TOKEN_ENV, "").strip()


def make_client(url: str, token: str) -> httpx.Client:
    return httpx.Client(base_url=url, headers={"X-Admin-Token": token}, timeout=30.0)


def fetch_page(client: httpx.Client, mode: str, after: str | None, limit: int = PAGE_LIMIT) -> dict:
    params = {"mode": mode, "limit": limit}
    if after:
        params["after"] = after
    try:
        response = client.get("/v1/admin/labels", params=params)
    except httpx.HTTPError as exc:
        raise AdminError(f"서버에 연결하지 못했습니다 ({type(exc).__name__})") from exc
    if response.status_code == 401:
        raise AdminError("관리자 토큰이 맞지 않습니다")
    if response.status_code == 404:
        raise AdminError("서버의 관리자 API 가 꺼져 있습니다(서버 .env 에 ADMIN_TOKEN 이 없다)")
    if response.status_code == 429:
        raise AdminError("요청이 너무 많아 서버가 잠시 막았습니다. 잠시 뒤에 다시 시도하세요")
    if response.status_code != 200:
        raise AdminError(f"서버가 오류를 돌려줬습니다 (HTTP {response.status_code})")
    return response.json()


def fetch_all(client: httpx.Client, mode: str) -> list[dict]:
    items: list[dict] = []
    after = None
    while True:
        page = fetch_page(client, mode, after)
        items.extend(page.get("labels", []))
        after = page.get("next")
        if not after:
            return items


def _resolution(item: dict) -> str:
    label = item["label"]
    return f"{label.get('sourceWidth')}x{label.get('sourceHeight')}"


def summarize(items: list[dict]) -> dict:
    per_install: dict[str, dict] = {}
    for it in items:
        row = per_install.setdefault(
            it["installId"], {"installId": it["installId"], "count": 0, "combat": 0, "other": 0, "lastReceivedAt": None}
        )
        row["count"] += 1
        kind = it["label"].get("userLabel")
        if kind in ("combat", "other"):
            row[kind] += 1
        row["lastReceivedAt"] = max(filter(None, [row["lastReceivedAt"], it.get("receivedAt")]), default=None)
    received = [it["receivedAt"] for it in items if it.get("receivedAt")]
    return {
        "total": len(items),
        "installs": len(per_install),
        "byLabel": dict(Counter(it["label"].get("userLabel") for it in items)),
        "byVersion": dict(sorted(Counter(it.get("appVersion") for it in items).items())),
        "byResolution": dict(Counter(_resolution(it) for it in items)),
        "byDay": dict(sorted(Counter(it["receivedAt"][:10] for it in items if it.get("receivedAt")).items())),
        "lastReceivedAt": max(received, default=None),
        "perInstall": sorted(per_install.values(), key=lambda r: (-r["count"], r["installId"])),
    }


def filter_items(items: list[dict], q: str = "", user_label: str = "") -> list[dict]:
    needle = q.strip().lower()
    result = []
    for it in items:
        if user_label and it["label"].get("userLabel") != user_label:
            continue
        if needle and not (
            it["installId"].lower().startswith(needle) or needle in str(it["label"].get("clipKey", "")).lower()
        ):
            continue
        result.append(it)
    return result
