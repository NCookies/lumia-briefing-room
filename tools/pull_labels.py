"""서버에 쌓인 라벨을 로컬로 가져와 `eval_pvp.py` 가 읽는 형태로 저장한다. (docs/roadmap.md §4-3, plan-infra.md)

usage:
    set LUMIA_ADMIN_TOKEN=...                     # 서버 관리자 토큰(업로드용 토큰과 다르다). 화면에 출력하지 않는다
    python tools/pull_labels.py [--out DIR] [--mode release|dev] [--full] [--url URL]
    python tools/eval_pvp.py DIR                  # 가져온 라벨로 점수를 평가한다

`DIR/.labels/<clipKey>.json` 으로 저장한다(서버의 combat/other 를 로컬의 pvp/pve 로 되돌린다).
마지막으로 받은 위치를 `DIR/.pull_state.json` 에 저장해 두므로 다음에는 새로 온(또는 고쳐서 다시 온) 라벨만 받는다. `--full` 은 처음부터 다시 받는다.
개발 모드 데이터(`--mode dev`)는 `DIR/dev/` 아래에 따로 둔다.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx

TOKEN_ENV = "LUMIA_ADMIN_TOKEN"
PAGE_LIMIT = 500
LOCAL_LABELS = {"combat": "pvp", "other": "pve"}


class PullError(Exception):
    pass


@dataclass
class PullResult:
    count: int = 0
    combat: int = 0
    other: int = 0
    installs: int = 0
    cursor: str | None = None
    seen_installs: set = field(default_factory=set)


def _local_record(item: dict) -> dict:
    label = dict(item["label"])
    label["userLabel"] = LOCAL_LABELS.get(label.get("userLabel"), label.get("userLabel"))
    label["id"] = label.get("clipKey")
    for key in ("installId", "receivedAt", "appVersion", "schemaVersion"):
        label[key] = item.get(key)
    return label


def _fetch_page(client: httpx.Client, mode: str, after: str | None) -> dict:
    params = {"mode": mode, "limit": PAGE_LIMIT}
    if after:
        params["after"] = after
    try:
        response = client.get("/v1/admin/labels", params=params)
    except httpx.HTTPError as exc:
        raise PullError(f"서버에 연결하지 못했습니다 ({type(exc).__name__})") from exc
    if response.status_code == 401:
        raise PullError("관리자 토큰이 맞지 않습니다")
    if response.status_code == 404:
        raise PullError("서버의 관리자 API 가 꺼져 있습니다(서버 .env 에 ADMIN_TOKEN 이 없다)")
    if response.status_code == 429:
        raise PullError("요청이 너무 많아 서버가 잠시 막았습니다. 잠시 뒤에 다시 시도하세요")
    if response.status_code != 200:
        raise PullError(f"서버가 오류를 돌려줬습니다 (HTTP {response.status_code})")
    return response.json()


def pull(client: httpx.Client, out: Path, *, mode: str, full: bool = False) -> PullResult:
    base = out / "dev" if mode == "dev" else out
    labels_dir = base / ".labels"
    state_path = base / ".pull_state.json"
    after = None
    if not full and state_path.exists():
        try:
            after = json.loads(state_path.read_text(encoding="utf-8")).get("cursor")
        except (OSError, ValueError):
            after = None
    result = PullResult(cursor=after)
    labels_dir.mkdir(parents=True, exist_ok=True)
    while True:
        page = _fetch_page(client, mode, after)
        for item in page.get("labels", []):
            record = _local_record(item)
            (labels_dir / f"{record['id']}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            result.count += 1
            result.combat += record["userLabel"] == "pvp"
            result.other += record["userLabel"] == "pve"
            result.seen_installs.add(item.get("installId"))
        if page.get("cursor"):
            result.cursor = page["cursor"]
            state_path.write_text(json.dumps({"cursor": result.cursor}), encoding="utf-8")
        after = page.get("next")
        if not after:
            break
    result.installs = len(result.seen_installs)
    return result


def main(argv: list[str] | None = None, *, transport: httpx.BaseTransport | None = None) -> int:
    parser = argparse.ArgumentParser(description="서버에 쌓인 라벨을 로컬로 가져온다")
    parser.add_argument("--out", type=Path, default=Path("pulled_labels"))
    parser.add_argument("--mode", choices=("release", "dev"), default="release")
    parser.add_argument("--url", default=os.environ.get("LUMIA_RECEIVER_URL"))
    parser.add_argument("--full", action="store_true", help="저장된 위치를 무시하고 처음부터 받는다")
    args = parser.parse_args(argv)

    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        print(f"관리자 토큰이 없습니다. 환경변수 {TOKEN_ENV} 에 서버 관리자 토큰을 넣고 다시 실행하세요", file=sys.stderr)
        return 2
    if not args.url:
        print("서버 주소가 없습니다. --url 이나 환경변수(또는 .env) LUMIA_RECEIVER_URL 에 넣고 다시 실행하세요", file=sys.stderr)
        return 2
    client = httpx.Client(base_url=args.url.rstrip("/"), headers={"X-Admin-Token": token}, timeout=30.0, transport=transport)
    try:
        result = pull(client, args.out, mode=args.mode, full=args.full)
    except PullError as exc:
        print(f"실패: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()
    where = (args.out / "dev" if args.mode == "dev" else args.out) / ".labels"
    print(f"라벨 {result.count}개를 받았다 (교전 {result.combat}, 그 외 {result.other}, 설치 {result.installs}개) → {where}")
    print(f"평가: python tools/eval_pvp.py {where.parent}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from envfile import load_env_file

    load_env_file(Path(__file__).resolve().parents[1] / ".env")
    raise SystemExit(main())
