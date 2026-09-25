"""서버에 쌓인 라벨을 보는 관리자 전용 대시보드(내 PC 에서만 띄운다). (plan-infra.md §8)

usage:
    set LUMIA_ADMIN_TOKEN=...          # 서버 관리자 토큰(.env 에 둬도 된다). 브라우저에는 넘기지 않고 이 프로세스만 쓴다
    python tools/admin_dashboard.py [--url URL] [--port 8100] [--no-open]

앱(run.bat)과 별개의 진입점이다. 127.0.0.1 에만 바인드하고, 서버 응답은 메모리에만 두며 화면의 "새로고침"으로 다시 받는다.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from collections import Counter
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pull_labels import TOKEN_ENV, PullError, _fetch_page  # noqa: E402

INDEX = Path(__file__).resolve().parent / "admin_dashboard" / "index.html"
MAX_LIMIT = 500


def fetch_all(client: httpx.Client, mode: str) -> list[dict]:
    items: list[dict] = []
    after = None
    while True:
        page = _fetch_page(client, mode, after)
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


def create_app(client: httpx.Client) -> FastAPI:
    app = FastAPI(title="루미아 관리자 대시보드")
    cache: dict[str, list[dict]] = {}
    lock = threading.Lock()

    def load(mode: str, refresh: bool) -> list[dict]:
        with lock:
            if refresh or mode not in cache:
                try:
                    cache[mode] = fetch_all(client, mode)
                except PullError as exc:
                    raise HTTPException(502, str(exc)) from exc
            return cache[mode]

    @app.get("/api/summary")
    def get_summary(mode: str = Query("release", pattern="^(release|dev)$"), refresh: bool = False):
        return summarize(load(mode, refresh))

    @app.get("/api/labels")
    def get_labels(
        mode: str = Query("release", pattern="^(release|dev)$"),
        q: str = "",
        userLabel: str = "",
        limit: int = Query(100, ge=1, le=MAX_LIMIT),
        offset: int = Query(0, ge=0),
        refresh: bool = False,
    ):
        found = filter_items(load(mode, refresh), q, userLabel)
        found.sort(key=lambda it: it.get("receivedAt") or "", reverse=True)
        return {"total": len(found), "items": found[offset : offset + limit]}

    @app.get("/")
    def index():
        return FileResponse(INDEX, media_type="text/html")

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="서버 라벨 관리자 대시보드(로컬 전용)")
    parser.add_argument("--url", default=os.environ.get("LUMIA_RECEIVER_URL"))
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)

    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        print(f"관리자 토큰이 없습니다. 환경변수(또는 .env) {TOKEN_ENV} 에 서버 관리자 토큰을 넣고 다시 실행하세요", file=sys.stderr)
        return 2
    if not args.url:
        print("서버 주소가 없습니다. --url 이나 환경변수(또는 .env) LUMIA_RECEIVER_URL 에 넣고 다시 실행하세요", file=sys.stderr)
        return 2
    client = httpx.Client(base_url=args.url.rstrip("/"), headers={"X-Admin-Token": token}, timeout=30.0)
    address = f"http://127.0.0.1:{args.port}/"
    print(f"관리자 대시보드: {address}  (종료: Ctrl+C)")
    if not args.no_open:
        threading.Timer(1.0, webbrowser.open, args=(address,)).start()
    try:
        uvicorn.run(create_app(client), host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    from envfile import load_env_file

    load_env_file(Path(__file__).resolve().parents[1] / ".env")
    raise SystemExit(main())
