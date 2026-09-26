"""앱 안 업데이트를 릴리스 없이 시험하는 로컬 가짜 GitHub 릴리스 서버. (plan-deploy.md D9)

usage:
  python tools/fake_release_server.py dist\\LumiaBriefingRoom-0.1.3-setup.exe --version 9.9.9 [--port 8770] [--notes-file notes.md]

주어진 설치기를 "v<버전>" 릴리스인 것처럼 GitHub Releases API 모양으로 내려주고(설치기·`.sha256` 포함), 앱을 아래 환경변수와 함께 실행하면
앱이 진짜 GitHub 대신 이 서버를 본다(두 값이 모두 127.0.0.1/localhost 일 때만 적용된다):

  LUMIA_UPDATE_API_URL=http://127.0.0.1:8770/repos/test/app/releases/latest
  LUMIA_UPDATE_DOWNLOAD_PREFIX=http://127.0.0.1:8770/download/

"버전" 은 앱의 현재 버전보다 커야 새 버전으로 보인다. 설치기 파일 자체의 버전은 상관없다(파일을 그대로 내려줄 뿐).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

API_PATH = "/repos/test/app/releases/latest"
DOWNLOAD_PATH = "/download/"
DEFAULT_NOTES = "### 시험 릴리스\n- 로컬 시험 서버가 내려주는 가짜 릴리스입니다.\n- **설치기는 그대로** 내려주고 체크섬도 같이 만듭니다.\n"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_routes(installer: Path, version: str, base: str, notes: str = DEFAULT_NOTES) -> dict[str, tuple[int, bytes | Path]]:
    """경로 → (상태, 본문 또는 파일 경로). 파일은 메모리에 올리지 않고 그대로 흘려 보낸다."""
    name = installer.name
    prefix = f"{DOWNLOAD_PATH}v{version}/"
    checksum = f"{sha256_of(installer)} *{name}\n".encode("utf-8")
    payload = {
        "tag_name": f"v{version}",
        "name": f"v{version}",
        "draft": False,
        "prerelease": False,
        "body": notes,
        "html_url": f"{base}/release/v{version}",
        "assets": [
            {"name": name, "browser_download_url": f"{base}{prefix}{name}"},
            {"name": f"{name}.sha256", "browser_download_url": f"{base}{prefix}{name}.sha256"},
        ],
    }
    return {
        API_PATH: (200, json.dumps(payload, ensure_ascii=False).encode("utf-8")),
        f"{prefix}{name}": (200, installer),
        f"{prefix}{name}.sha256": (200, checksum),
    }


def make_server(routes: dict, port: int = 0) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, body = routes.get(self.path, (404, b"not found"))
            size = body.stat().st_size if isinstance(body, Path) else len(body)
            self.send_response(status)
            self.send_header("Content-Length", str(size))
            self.end_headers()
            if isinstance(body, Path):
                with body.open("rb") as handle:
                    while chunk := handle.read(1 << 20):
                        self.wfile.write(chunk)
            else:
                self.wfile.write(body)

        def log_message(self, fmt, *args):
            print("[fake-release]", self.address_string(), fmt % args, flush=True)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("installer", type=Path, help="새 버전인 것처럼 내려줄 설치기(*-setup.exe)")
    parser.add_argument("--version", required=True, help="가짜 릴리스 버전(앱 현재 버전보다 커야 한다, 예 9.9.9)")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--notes-file", type=Path, help="릴리스 본문(마크다운). 없으면 기본 문구")
    args = parser.parse_args(argv)

    if not args.installer.is_file() or not args.installer.name.endswith("-setup.exe"):
        print("설치기 파일(…-setup.exe)이 아니다:", args.installer, file=sys.stderr)
        return 2
    notes = args.notes_file.read_text(encoding="utf-8") if args.notes_file else DEFAULT_NOTES
    routes: dict = {}
    server = make_server(routes, args.port)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    routes.update(build_routes(args.installer, args.version, base, notes))
    print(f"가짜 릴리스 서버: {base}  (v{args.version} ← {args.installer.name})")
    print("앱을 아래 환경변수와 함께 실행하세요(PowerShell):")
    print(f'  $env:LUMIA_UPDATE_API_URL = "{base}{API_PATH}"')
    print(f'  $env:LUMIA_UPDATE_DOWNLOAD_PREFIX = "{base}{DOWNLOAD_PATH}"')
    print("Ctrl+C 로 끝냅니다.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
