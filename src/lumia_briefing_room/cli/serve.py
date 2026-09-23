"""API(+ 빌드된 프론트)를 uvicorn 으로 띄우고 pywebview(또는 기본 브라우저)로 연다.

uvicorn 은 백그라운드 스레드에서 돌리고, pywebview 의 webview.start() 는 메인
스레드에서 호출한다 (plan-ui.md §4-1). pywebview 가 없거나 실행에 실패하면
기본 브라우저로 여는 것으로 대체한다.
"""

import argparse
import logging
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from lumia_briefing_room.api.app import create_app
from lumia_briefing_room.api.static import find_frontend_dist, mount_static
from lumia_briefing_room import startup
from lumia_briefing_room.config import Config, load_config, resolve_config_path

log = logging.getLogger("lumia_briefing_room.serve")


def build_app(cfg: Config, *, config_path: Path | None = None):
    app = create_app(cfg, config_path=config_path)
    dist_dir = find_frontend_dist()
    if dist_dir is not None:
        mount_static(app, dist_dir)
    else:
        log.warning("frontend/dist 를 찾을 수 없다 - API 만 뜬다 (frontend 에서 npm run build 필요)")
    return app


def wait_until_started(
    server: uvicorn.Server,
    *,
    timeout: float = 5.0,
    sleep=time.sleep,
    now=time.monotonic,
) -> bool:
    deadline = now() + timeout
    while not server.started:
        if now() >= deadline:
            return False
        sleep(0.05)
    return True


def run_server_in_thread(
    app, *, host: str = "127.0.0.1", port: int = 8000
) -> tuple[uvicorn.Server, threading.Thread]:
    # log_config=None: 콘솔 없는 빌드(sys.stdout 이 None)에서 uvicorn 의 기본 로깅 설정이
    # ColourizedFormatter → sys.stdout.isatty() 로 터져 서버가 아예 안 뜬다. 로그는 logsetup 이 파일로 받는다.
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", log_config=None)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread


def open_ui(url: str) -> None:
    try:
        import webview
    except ImportError:
        webbrowser.open(url)
        return
    try:
        webview.create_window("루미아 브리핑룸", url, width=1280, height=900)
        webview.start()
    except Exception:
        log.exception("pywebview 실행 실패 - 기본 브라우저로 연다")
        webbrowser.open(url)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="루미아 브리핑룸 열람 UI 서버")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> None:
    startup.setup_logging()
    startup.install_excepthooks()
    args = build_parser().parse_args(argv)

    config_path = resolve_config_path(args.config)
    cfg = load_config(config_path)
    app = build_app(cfg, config_path=config_path)
    server, thread = run_server_in_thread(app, host=args.host, port=args.port)

    if not wait_until_started(server):
        log.error("서버가 제한 시간 안에 시작되지 않았다")
        return

    try:
        open_ui(f"http://{args.host}:{args.port}/")
    finally:
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
